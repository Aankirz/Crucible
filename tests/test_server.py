"""Unit tests for the FastAPI Mission Control server (crucible.server.app).

Everything that would touch the network, real credentials, or data files is
monkeypatched: `init_tracing` (startup), and for `/run` the data loaders,
`gemini_model`, and `run_loop`. The pure `EventBus` is tested directly.
"""
from __future__ import annotations

import asyncio
import threading
import time

import pytest
from fastapi.testclient import TestClient

from crucible.server import app as app_module
from crucible.server.events import EventBus


@pytest.fixture(autouse=True)
def _no_tracing(monkeypatch):
    """Stub Phoenix tracing so the app starts up without credentials."""
    monkeypatch.setattr(app_module, "init_tracing", lambda: None)


@pytest.fixture
def client():
    with TestClient(app_module.app) as c:
        yield c


@pytest.fixture(autouse=True)
def _reset_run_state():
    """Keep the shared module-level run state isolated between tests.

    Also clears the bus's event-loop binding: a previous TestClient binds the
    module-level bus to its (now-closed) loop, which would break a later
    direct publish. Tests that need a live binding re-bind via the client fixture.
    """
    app_module._run_state.update({"autopilot": True, "running": False})
    app_module._approval_gate.clear()
    app_module.bus._loop = None
    yield
    app_module._run_state.update({"autopilot": True, "running": False})
    app_module._approval_gate.clear()
    app_module.bus._loop = None


# --- EventBus (pure) ---------------------------------------------------------


def test_event_bus_publish_reaches_subscriber():
    bus = EventBus()
    q = bus.subscribe()

    event = {"type": "version", "version": 1, "train": 0.5, "test": 0.4}
    bus.publish(event)

    assert q.get_nowait() == event


def test_event_bus_fans_out_to_all_subscribers():
    bus = EventBus()
    q1 = bus.subscribe()
    q2 = bus.subscribe()

    bus.publish({"type": "rejected", "version": 2})

    assert q1.get_nowait() == {"type": "rejected", "version": 2}
    assert q2.get_nowait() == {"type": "rejected", "version": 2}


def test_event_bus_subscriber_only_sees_events_after_subscribing():
    bus = EventBus()
    bus.publish({"type": "version", "version": 1})  # no subscribers yet
    q = bus.subscribe()
    bus.publish({"type": "version", "version": 2})

    assert q.get_nowait() == {"type": "version", "version": 2}
    assert q.empty()


# --- app construction --------------------------------------------------------


def test_app_imports_and_client_constructs(client):
    assert app_module.app.title == "Crucible Mission Control"


# --- /databases & /schema ----------------------------------------------------


def test_databases_returns_catalog(client):
    resp = client.get("/databases")
    assert resp.status_code == 200
    body = resp.json()
    assert "databases" in body
    ids = [d["id"] for d in body["databases"]]
    assert "world" in ids
    assert {"concert_singer", "university", "ecommerce"} <= set(ids)
    # Every entry carries the frozen contract fields.
    for d in body["databases"]:
        assert set(d) == {
            "id", "name", "domain", "tables",
            "num_questions", "mode", "blurb",
        }


def test_databases_marks_modes(client):
    body = client.get("/databases").json()
    modes = {d["id"]: d["mode"] for d in body["databases"]}
    assert modes["world"] == "demo"
    assert modes["concert_singer"] == "live"
    assert modes["university"] == "live"
    assert modes["ecommerce"] == "live"


def test_schema_returns_ddl_for_known_db(client):
    resp = client.get("/schema", params={"db_id": "university"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["db_id"] == "university"
    assert "CREATE TABLE" in body["schema"]


def test_schema_unknown_db_returns_empty(client):
    body = client.get("/schema", params={"db_id": "nope"}).json()
    assert body["db_id"] == "nope"
    assert body["schema"] == ""


def test_run_live_db_reports_live_mode(client, monkeypatch):
    """Catalog 'live' db_id dispatches the live worker and reports mode=live."""
    started = threading.Event()
    monkeypatch.setattr(
        app_module, "_run_live_job",
        lambda db_id: (started.set(), app_module._run_state.update(running=False)),
    )
    resp = client.post("/run", params={"db_id": "ecommerce", "autopilot": True})
    assert resp.status_code == 200
    body = resp.json()
    assert body["started"] is True
    assert body["db_id"] == "ecommerce"
    assert body["mode"] == "live"
    assert started.wait(timeout=5.0)


def test_run_world_reports_demo_mode(client, monkeypatch):
    """Catalog 'world' db_id dispatches the demo worker and reports mode=demo."""
    started = threading.Event()
    monkeypatch.setattr(
        app_module, "_run_demo_job",
        lambda db_id: (started.set(), app_module._run_state.update(running=False)),
    )
    resp = client.post("/run", params={"db_id": "world"})
    assert resp.status_code == 200
    assert resp.json()["mode"] == "demo"
    assert started.wait(timeout=5.0)


# --- /approve ----------------------------------------------------------------


def test_approve_returns_ok_and_sets_gate(client):
    assert not app_module._approval_gate.is_set()

    resp = client.post("/approve")

    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    assert app_module._approval_gate.is_set()


# --- /events -----------------------------------------------------------------


# NOTE: the live HTTP SSE stream (`GET /events`) is intentionally NOT unit-tested.
# Starlette's TestClient cannot cleanly close an infinite event-generator response,
# so any test that opens the stream hangs on teardown. SSE delivery semantics are
# covered by the EventBus tests + the cross-thread test below; the HTTP stream is
# verified live against the running server + UI.


def test_event_bus_cross_thread_delivery_with_bound_loop():
    """HIGH-2 regression: a publish from a worker thread must reach a subscriber
    awaiting in the event loop. Without thread-safe scheduling this would hang."""

    async def scenario():
        bus = EventBus()
        bus.bind_loop(asyncio.get_running_loop())
        q = bus.subscribe()
        event = {"type": "version", "version": 1, "train": 0.5, "test": 0.4}
        # publish from a different thread, as the real loop does
        threading.Thread(target=bus.publish, args=(event,)).start()
        received = await asyncio.wait_for(q.get(), timeout=2.0)
        assert received == event

    asyncio.run(scenario())


# --- /run --------------------------------------------------------------------


def test_run_starts_loop_and_invokes_orchestrator(client, monkeypatch):
    """Drive /run end-to-end with stubbed data loaders, model, and run_loop."""
    captured = {}
    done = threading.Event()

    monkeypatch.setenv("CRUCIBLE_DB_PATH", "/tmp/does-not-need-to-exist.db")
    monkeypatch.setattr(app_module, "read_schema", lambda path: "CREATE TABLE t(x)")
    monkeypatch.setattr(
        app_module, "_build_splits", lambda db_id: (["train-item"], ["test-item"])
    )
    monkeypatch.setattr(app_module, "gemini_model", lambda: (lambda p: "SELECT 1"))

    def fake_run_loop(**kwargs):
        captured.update(kwargs)
        # Exercise the event relay path that the real loop would use.
        kwargs["on_event"]({"type": "version", "version": 1, "train": 1.0, "test": 1.0})
        done.set()

    monkeypatch.setattr(app_module, "run_loop", fake_run_loop)

    resp = client.post("/run", params={"db_id": "world_1", "autopilot": True})

    assert resp.status_code == 200
    # "world_1" is unknown to the catalog -> legacy env dispatch (CRUCIBLE_DEMO
    # unset here) reports mode="live". `mode` was added per the v2 contract.
    assert resp.json() == {
        "started": True, "db_id": "world_1", "mode": "live", "autopilot": True,
    }

    assert done.wait(timeout=5.0), "loop thread did not run"

    assert captured["db_id"] == "world_1"
    assert captured["train"] == ["train-item"]
    assert captured["test"] == ["test-item"]
    assert captured["schema_ddl"] == "CREATE TABLE t(x)"
    assert captured["config"] is app_module.LOOP_CONFIG

    # running flag reset after the loop completes.
    for _ in range(100):
        if not app_module._run_state["running"]:
            break
        time.sleep(0.01)
    assert app_module._run_state["running"] is False


def test_run_rejects_when_already_running(client):
    app_module._run_state["running"] = True

    resp = client.post("/run", params={"db_id": "world_1"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["started"] is False
    assert "in progress" in body["reason"]


def test_run_loop_job_publishes_error_on_failure(monkeypatch):
    """Failures inside the loop are surfaced as an error event, flag reset."""
    monkeypatch.setenv("CRUCIBLE_DB_PATH", "/tmp/whatever.db")
    monkeypatch.setattr(app_module, "read_schema", lambda path: "ddl")
    monkeypatch.setattr(
        app_module, "_build_splits", lambda db_id: (["t"], ["v"])
    )
    monkeypatch.setattr(app_module, "gemini_model", lambda: (lambda p: ""))

    def boom(**kwargs):
        raise RuntimeError("loop exploded")

    monkeypatch.setattr(app_module, "run_loop", boom)
    app_module._run_state["running"] = True

    q = app_module.bus.subscribe()
    app_module._run_loop_job("world_1")

    assert q.get_nowait() == {"type": "error", "message": "loop exploded"}
    assert app_module._run_state["running"] is False
