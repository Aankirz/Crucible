"""Crucible "Mission Control" FastAPI backend.

Exposes the reflexive text-to-SQL optimization loop as a Server-Sent Events
(SSE) stream plus control endpoints for the React UI:

  GET  /events            -> SSE stream of loop events (version/hypothesis/...)
  POST /run               -> start a loop in a background thread
  POST /approve           -> release the human-approval gate (non-autopilot runs)

The deterministic core (orchestrator, eval engine, sandbox) is imported as-is;
this module only wires it to HTTP, an in-memory event bus, and Phoenix tracing.

Per plan Task 7.1. The orchestrator runs in a daemon thread (it is synchronous
and CPU/IO bound); its `on_event` callback fans events out over the async
`EventBus` to every connected SSE client.
"""
from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import threading
import time
from typing import Any, AsyncIterator

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

from crucible.datasets.spider_loader import load_spider_dev
from crucible.datasets.split import stratified_split, weighted_sample
from crucible.datasets.world_bundle import (
    WORLD_TEST,
    WORLD_TRAIN,
    build_world_db,
)
from crucible.models import gemini_model
from crucible.mcp_introspect import introspect_failures
from crucible.orchestrator import LoopConfig, run_loop
from crucible.phoenix_client import init_tracing, log_experiment
from crucible.sandbox import SqlSandbox
from crucible.server.events import EventBus
from crucible.types import CandidateSpec

load_dotenv()

# --- Loop defaults (plan Task 7.1) -------------------------------------------
DEFAULT_DB_ID = "world_1"
SAMPLE_SIZE = 70
TEST_FRACTION = 0.43
SAMPLE_SEED = 0
INITIAL_SYSTEM_PROMPT = "You are an expert SQLite analyst. Output only SQL."
LOOP_CONFIG = LoopConfig(max_iters=5, target=0.9, patience=2)

# Read-only DDL query: every table's CREATE statement.
_SCHEMA_QUERY = (
    "SELECT sql FROM sqlite_master WHERE type='table' AND sql IS NOT NULL"
)

# How long the loop thread waits for a human approval before promoting anyway.
APPROVAL_TIMEOUT_S = 120.0


def read_schema(db_path: str) -> str:
    """Return the concatenated CREATE TABLE DDL for a SQLite database.

    Opens the database read-only so this helper can never mutate the file.

    Args:
        db_path: Filesystem path to the SQLite database.

    Returns:
        Newline-joined `CREATE TABLE` statements (empty string if none).
    """
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        ddl = "\n".join(row[0] for row in conn.execute(_SCHEMA_QUERY))
    finally:
        conn.close()
    return ddl


app = FastAPI(title="Crucible Mission Control")

# Permissive CORS: the Vite dev server runs on a different origin/port.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Single in-process event bus shared by the loop thread and all SSE clients.
bus = EventBus()

# Path to the self-contained "world" database, built at startup when no external
# Spider/BIRD data is configured (the hosted-demo case). Lets the server run the
# REAL loop on a real DB with real gold SQL without a license-bound download.
_bundled_db_path: str | None = None


def _spider_configured() -> bool:
    """True when a real Spider dev file is configured and present on disk."""
    spider_dev = os.environ.get("CRUCIBLE_SPIDER_DEV")
    return bool(spider_dev) and os.path.exists(spider_dev)

# Human-approval gate. `event` is released by POST /approve; `autopilot` toggles
# whether the loop thread blocks on it before relaying the final `promoted`.
_approval_gate = threading.Event()
_run_state: dict[str, Any] = {"autopilot": True, "running": False}


@app.on_event("startup")
def _startup() -> None:
    """Initialise Phoenix tracing, tolerating absent credentials.

    Wrapped in try/except so the server still boots in environments without
    Phoenix configuration (e.g. local UI development, CI smoke imports).
    """
    # Bind the running loop so the worker thread can publish events thread-safely.
    bus.bind_loop(asyncio.get_running_loop())

    # When no external Spider/BIRD data is configured, build the self-contained
    # world DB so /run can execute the real loop on real data out of the box.
    global _bundled_db_path
    if not _spider_configured():
        try:
            _bundled_db_path = build_world_db()
            print(f"[crucible] bundled world DB ready at {_bundled_db_path}")
        except Exception as exc:  # noqa: BLE001 - never block boot on data setup.
            print(f"[crucible] bundled world DB unavailable: {exc}")

    try:
        init_tracing()
    except Exception as exc:  # noqa: BLE001 - boot must not depend on Phoenix.
        print(f"[crucible] tracing disabled: {exc}")


@app.get("/healthz")
def healthz() -> dict[str, Any]:
    """Liveness probe + a tiny status payload for the host's health check."""
    return {
        "ok": True,
        "service": "crucible-mission-control",
        "dataset": "spider" if _spider_configured() else "world",
        "running": _run_state["running"],
    }


@app.get("/events")
async def stream_events() -> EventSourceResponse:
    """SSE endpoint: stream JSON-encoded loop events to a connected client."""
    queue = bus.subscribe()

    async def event_generator() -> AsyncIterator[dict[str, str]]:
        while True:
            event = await queue.get()
            yield {"data": json.dumps(event)}

    return EventSourceResponse(event_generator())


@app.post("/approve")
def approve() -> dict[str, bool]:
    """Release the human-approval gate so a blocked loop can promote."""
    _approval_gate.set()
    return {"ok": True}


@app.post("/run")
def run(db_id: str = DEFAULT_DB_ID, autopilot: bool = True) -> dict[str, Any]:
    """Start an optimization loop for `db_id` in a background daemon thread.

    Args:
        db_id: Spider/BIRD database id to optimize against.
        autopilot: When False, the loop blocks before promoting the final best
            candidate until POST /approve is called (or `APPROVAL_TIMEOUT_S`).

    Returns:
        A small JSON ack; loop progress is delivered over GET /events.
    """
    if _run_state["running"]:
        return {"started": False, "reason": "a run is already in progress"}

    _run_state["autopilot"] = autopilot
    _run_state["running"] = True
    _approval_gate.clear()

    target = _run_demo_job if _demo_mode() else _run_loop_job
    thread = threading.Thread(
        target=target,
        args=(db_id,),
        name=f"crucible-loop-{db_id}",
        daemon=True,
    )
    thread.start()
    return {"started": True, "db_id": db_id, "autopilot": autopilot}


def _demo_mode() -> bool:
    """True when CRUCIBLE_DEMO is set: /run streams the deterministic climb.

    Demo mode runs the REAL optimization loop (real SQL, real execution-match
    scores) with a deterministic model standing in for Gemini, so the hosted UI
    shows a genuine 50%->100% climb without a funded LLM. Not replay: every score
    is produced by executing SQL against the database during the run.
    """
    return (os.environ.get("CRUCIBLE_DEMO") or "").strip().lower() in (
        "1", "true", "yes", "on",
    )


def _relay_event(event: dict[str, Any]) -> None:
    """Forward a loop event to SSE clients, gating final promotion when manual.

    The orchestrator emits `promoted` last. In non-autopilot mode we block the
    loop thread here until a human calls /approve (bounded by a timeout) before
    the `promoted` event reaches the UI, modelling a human promotion gate.
    """
    if event.get("type") == "promoted" and not _run_state["autopilot"]:
        _approval_gate.wait(timeout=APPROVAL_TIMEOUT_S)
    bus.publish(event)


def _build_splits(db_id: str) -> tuple[list, list]:
    """Load the dataset for `db_id` and build train/test splits.

    Falls back to the self-contained bundled "world" benchmark when no Spider dev
    file is configured (the hosted-demo case), so the server runs the real loop on
    real data without an external download.

    Returns:
        A `(train, test)` tuple of `EvalItem` lists.
    """
    if not _spider_configured():
        return list(WORLD_TRAIN), list(WORLD_TEST)
    spider_dev = os.environ["CRUCIBLE_SPIDER_DEV"]
    items = load_spider_dev(spider_dev, db_id=db_id)
    pool = weighted_sample(items, n=SAMPLE_SIZE, seed=SAMPLE_SEED)
    return stratified_split(pool, test_frac=TEST_FRACTION, seed=SAMPLE_SEED)


def _run_loop_job(db_id: str) -> None:
    """Background worker: run the full optimization loop for `db_id`.

    Reads configuration from the environment (`CRUCIBLE_DB_PATH`,
    `CRUCIBLE_SPIDER_DEV`, `GEMINI_MODEL` via `gemini_model`). Always resets the
    running flag, even on failure, so subsequent runs can start.
    """
    try:
        # In bundled-world mode, use the DB built at startup; otherwise the
        # configured Spider/BIRD database path.
        world_mode = not _spider_configured()
        db_path = (
            _bundled_db_path
            if world_mode and _bundled_db_path
            else os.environ["CRUCIBLE_DB_PATH"]
        )
        schema_ddl = read_schema(db_path)
        train, test = _build_splits(db_id)
        model = gemini_model()  # honours GEMINI_MODEL; candidate == mutation model
        run_loop(
            # World mode starts WITHOUT the schema so the agent must earn it from
            # its own failures — an honest climb. File-backed datasets keep the
            # schema since their tables are unknown to the agent up front.
            initial_spec=CandidateSpec(
                1, INITIAL_SYSTEM_PROMPT, enable_schema=not world_mode
            ),
            schema_ddl=schema_ddl,
            train=train,
            test=test,
            sandbox=SqlSandbox(db_path),
            candidate_model=model,
            mutation_model=model,
            introspect=introspect_failures,
            log_experiment=log_experiment,
            on_event=_relay_event,
            db_id=db_id,
            config=LOOP_CONFIG,
        )
    except Exception as exc:  # noqa: BLE001 - surface failure to the UI stream.
        bus.publish({"type": "error", "message": str(exc)})
    finally:
        _run_state["running"] = False


# Pacing (seconds) between streamed demo events so the UI animates the climb
# rather than dumping every version at once.
_DEMO_EVENT_DELAY_S = 1.1


def _run_demo_job(db_id: str) -> None:
    """Background worker: stream the REAL optimization loop, paced for the UI.

    Demo mode runs `crucible.orchestrator.run_loop` on the bundled world DB with
    the deterministic scripted models from `scripts/offline_demo.py`. Every score
    is produced by executing SQL against the real database — this is the genuine
    50%->100% climb, not a replay — but it needs no funded LLM, so the hosted UI
    always shows a working run. A small delay paces each event for the leaderboard.
    """
    try:
        import sys
        from pathlib import Path

        scripts_dir = Path(__file__).resolve().parents[3] / "scripts"
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))

        # Reuse the offline demo's real DB builder + scripted (no-API) models.
        import offline_demo as demo  # type: ignore

        import tempfile

        tmp = tempfile.mkdtemp(prefix="crucible_demo_")
        db_path = str(Path(tmp) / "world.sqlite")
        demo.build_database(Path(db_path))

        def paced_relay(event: dict[str, Any]) -> None:
            _relay_event(event)
            time.sleep(_DEMO_EVENT_DELAY_S)

        run_loop(
            initial_spec=CandidateSpec(
                1, "You are an expert SQLite analyst. Output only SQL.",
                enable_schema=True,
            ),
            schema_ddl=demo.SCHEMA_DDL,
            train=demo.TRAIN,
            test=demo.TEST,
            sandbox=SqlSandbox(db_path),
            candidate_model=demo.make_candidate_model(),
            mutation_model=demo.make_mutation_model(),
            introspect=demo.introspect,
            # Fast local stub (no network) so the UI climb is snappy and never
            # blocks on Phoenix; real Phoenix logging is used by the live job.
            log_experiment=demo.log_experiment,
            on_event=paced_relay,
            db_id=db_id,
            config=LOOP_CONFIG,
        )
    except Exception as exc:  # noqa: BLE001 - surface failure to the UI stream.
        bus.publish({"type": "error", "message": str(exc)})
    finally:
        _run_state["running"] = False


# --- Static UI (single-service deploy) ---------------------------------------
# When CRUCIBLE_UI_DIST points at a built Vite bundle, serve it at "/" so one
# process hosts both the API and the Mission Control UI (same origin -> no CORS,
# no separate frontend deploy). Mounted LAST so the API routes above win; html=True
# serves index.html for "/" and any client-side path.
_ui_dist = os.environ.get("CRUCIBLE_UI_DIST")
if _ui_dist and os.path.isdir(_ui_dist):
    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=_ui_dist, html=True), name="ui")
