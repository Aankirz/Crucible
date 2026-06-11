"""Tests for the MCP introspection retry/fallback behavior.

The async ADK+Phoenix core is monkeypatched, so these tests never touch the
network, npx, or a model — they only verify the synchronous retry policy that
wraps it.
"""
from __future__ import annotations

import crucible.mcp_introspect as mod


def _no_sleep(monkeypatch):
    monkeypatch.setattr(mod.time, "sleep", lambda *_: None)


def test_is_transient_detects_overload_and_rate_limit():
    assert mod._is_transient(RuntimeError("503 UNAVAILABLE high demand"))
    assert mod._is_transient(Exception("429 RESOURCE_EXHAUSTED"))
    assert not mod._is_transient(KeyError("PHOENIX_API_KEY"))


def test_returns_summary_on_first_success(monkeypatch):
    _no_sleep(monkeypatch)
    calls = {"n": 0}

    def fake_run(_coro):
        _coro.close()  # we don't await it; avoid 'never awaited' warning
        calls["n"] += 1
        return "FAILURE: missing joins\nSCORE: 0.5"

    monkeypatch.setattr(mod.asyncio, "run", fake_run)
    out = mod.introspect_failures("exp-1")

    assert out.startswith("FAILURE:")
    assert calls["n"] == 1  # no retries needed on success


def test_retries_transient_then_succeeds(monkeypatch):
    _no_sleep(monkeypatch)
    attempts = {"n": 0}

    def fake_run(_coro):
        _coro.close()  # we don't await it; avoid 'never awaited' warning
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise RuntimeError("503 UNAVAILABLE: high demand")
        return "FAILURE: aggregation\nSCORE: 0.6"

    monkeypatch.setattr(mod.asyncio, "run", fake_run)
    out = mod.introspect_failures("exp-2")

    assert "aggregation" in out
    assert attempts["n"] == 2  # retried once after the transient error


def test_terminal_error_fails_fast_to_empty(monkeypatch):
    _no_sleep(monkeypatch)
    attempts = {"n": 0}

    def fake_run(_coro):
        _coro.close()  # we don't await it; avoid 'never awaited' warning
        attempts["n"] += 1
        raise KeyError("PHOENIX_API_KEY")  # terminal: not transient

    monkeypatch.setattr(mod.asyncio, "run", fake_run)
    out = mod.introspect_failures("exp-3")

    assert out == ""
    assert attempts["n"] == 1  # no retries on a terminal error


def test_exhausts_retries_then_returns_empty(monkeypatch):
    _no_sleep(monkeypatch)
    attempts = {"n": 0}

    def fake_run(_coro):
        _coro.close()  # we don't await it; avoid 'never awaited' warning
        attempts["n"] += 1
        raise RuntimeError("503 overloaded")

    monkeypatch.setattr(mod.asyncio, "run", fake_run)
    out = mod.introspect_failures("exp-4")

    assert out == ""
    assert attempts["n"] == mod._MAX_INTROSPECT_ATTEMPTS  # tried the full budget
