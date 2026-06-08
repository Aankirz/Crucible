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
from typing import Any, AsyncIterator

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

from crucible.datasets.spider_loader import load_spider_dev
from crucible.datasets.split import stratified_split, weighted_sample
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
    try:
        init_tracing()
    except Exception as exc:  # noqa: BLE001 - boot must not depend on Phoenix.
        print(f"[crucible] tracing disabled: {exc}")


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

    thread = threading.Thread(
        target=_run_loop_job,
        args=(db_id,),
        name=f"crucible-loop-{db_id}",
        daemon=True,
    )
    thread.start()
    return {"started": True, "db_id": db_id, "autopilot": autopilot}


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

    Returns:
        A `(train, test)` tuple of `EvalItem` lists.
    """
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
        db_path = os.environ["CRUCIBLE_DB_PATH"]
        schema_ddl = read_schema(db_path)
        train, test = _build_splits(db_id)
        model = gemini_model()  # honours GEMINI_MODEL; candidate == mutation model
        run_loop(
            initial_spec=CandidateSpec(
                1, INITIAL_SYSTEM_PROMPT, enable_schema=True
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
