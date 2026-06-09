"""Unit tests for the Phoenix SDK plumbing (crucible.phoenix_client).

The Phoenix SDK is imported lazily inside each function, so we patch the symbols
in the SDK modules that the code imports (`phoenix.otel.register`,
`phoenix.client.Client`, `phoenix.client.types.PromptVersion`) with fakes that
capture their arguments. No network or real Phoenix credentials are used.
"""
from __future__ import annotations

import sys
import types as pytypes

import pytest

from crucible import phoenix_client
from crucible.types import EvalItem, EvalResult, ItemResult


# --- fake SDK module installation -------------------------------------------


def _install_fake_otel(monkeypatch):
    """Install a fake `phoenix.otel` module with a call-capturing register()."""
    captured = {}

    def register(**kwargs):
        captured["kwargs"] = kwargs
        return "fake-tracer-provider"

    otel_mod = pytypes.ModuleType("phoenix.otel")
    otel_mod.register = register
    monkeypatch.setitem(sys.modules, "phoenix.otel", otel_mod)
    return captured


class _FakeDatasets:
    def __init__(self, sink):
        self._sink = sink

    def create_dataset(self, **kwargs):
        self._sink["dataset"] = kwargs
        return {"_dataset": kwargs["name"]}


class _FakeExperiments:
    def __init__(self, sink):
        self._sink = sink

    def run_experiment(self, **kwargs):
        self._sink["experiment"] = kwargs
        # Bare object with no name/id, forcing the deterministic-name fallback.
        return object()


class _FakePrompts:
    def __init__(self, sink):
        self._sink = sink

    def create(self, **kwargs):
        self._sink["prompt"] = kwargs


class _FakeClient:
    def __init__(self, sink, **kwargs):
        sink["client_kwargs"] = kwargs
        self.datasets = _FakeDatasets(sink)
        self.experiments = _FakeExperiments(sink)
        self.prompts = _FakePrompts(sink)


def _install_fake_client(monkeypatch):
    """Install a fake `phoenix.client` module; return the shared capture sink."""
    sink: dict = {}

    client_mod = pytypes.ModuleType("phoenix.client")
    client_mod.Client = lambda **kwargs: _FakeClient(sink, **kwargs)
    monkeypatch.setitem(sys.modules, "phoenix.client", client_mod)
    return sink


def _install_fake_prompt_types(monkeypatch, sink):
    """Install a fake `phoenix.client.types` with a recording PromptVersion."""

    class PromptVersion:
        def __init__(self, messages, model_name=None):
            self.messages = messages
            self.model_name = model_name
            sink["prompt_version"] = self

    types_mod = pytypes.ModuleType("phoenix.client.types")
    types_mod.PromptVersion = PromptVersion
    monkeypatch.setitem(sys.modules, "phoenix.client.types", types_mod)


# --- fixtures ----------------------------------------------------------------


@pytest.fixture
def eval_result():
    item_a = EvalItem(
        question="how many?", gold_sql="SELECT count(*) FROM t",
        db_id="world_1", difficulty="easy",
    )
    item_b = EvalItem(
        question="list names", gold_sql="SELECT name FROM t",
        db_id="world_1", difficulty="hard",
    )
    return EvalResult(
        spec_version=3,
        split="test",
        score=0.5,
        item_results=(
            ItemResult(item=item_a, predicted_sql="SELECT count(*) FROM t",
                       is_match=True, error=None),
            ItemResult(item=item_b, predicted_sql="SELECT bad",
                       is_match=False, error="syntax error"),
        ),
    )


# --- init_tracing ------------------------------------------------------------


def test_init_tracing_passes_project_and_endpoint(monkeypatch):
    captured = _install_fake_otel(monkeypatch)
    monkeypatch.setenv("PHOENIX_PROJECT_NAME", "myproj")
    monkeypatch.setenv("PHOENIX_COLLECTOR_ENDPOINT", "https://app.phoenix.example/")

    result = phoenix_client.init_tracing()

    assert result == "fake-tracer-provider"
    kwargs = captured["kwargs"]
    assert kwargs["project_name"] == "myproj"
    assert kwargs["auto_instrument"] is True
    # Trailing slash stripped, /v1/traces appended.
    assert kwargs["endpoint"] == "https://app.phoenix.example/v1/traces"


def test_init_tracing_defaults_project_and_omits_endpoint(monkeypatch):
    captured = _install_fake_otel(monkeypatch)
    monkeypatch.delenv("PHOENIX_PROJECT_NAME", raising=False)
    monkeypatch.delenv("PHOENIX_COLLECTOR_ENDPOINT", raising=False)

    phoenix_client.init_tracing()

    kwargs = captured["kwargs"]
    assert kwargs["project_name"] == phoenix_client._DEFAULT_PROJECT
    assert "endpoint" not in kwargs  # let register() fall back to its defaults


# --- log_experiment ----------------------------------------------------------


def test_log_experiment_shapes_dataset_rows(monkeypatch, eval_result):
    sink = _install_fake_client(monkeypatch)
    monkeypatch.setenv("PHOENIX_COLLECTOR_ENDPOINT", "https://p.example")
    monkeypatch.setenv("PHOENIX_API_KEY", "secret")

    returned = phoenix_client.log_experiment(eval_result, db_id="world_1")

    # Client constructed from env.
    assert sink["client_kwargs"] == {
        "base_url": "https://p.example",
        "api_key": "secret",
    }

    ds = sink["dataset"]
    # Deterministic name encodes db, version, split.
    assert ds["name"] == "crucible-world_1-v3-test"
    assert ds["inputs"] == [{"question": "how many?"}, {"question": "list names"}]
    assert ds["outputs"] == [
        {"gold_sql": "SELECT count(*) FROM t"},
        {"gold_sql": "SELECT name FROM t"},
    ]

    # metadata rows carry the full frozen contract per item.
    meta = ds["metadata"]
    assert meta[0] == {
        "question": "how many?",
        "gold_sql": "SELECT count(*) FROM t",
        "predicted_sql": "SELECT count(*) FROM t",
        "is_match": True,
        "error": None,
        "difficulty": "easy",
    }
    assert meta[1]["is_match"] is False
    assert meta[1]["error"] == "syntax error"
    assert meta[1]["difficulty"] == "hard"

    # Run-level execution_match metric equals the aggregate score.
    exp = sink["experiment"]
    assert exp["experiment_metadata"]["execution_match"] == eval_result.score
    assert exp["experiment_name"] == "crucible-world_1-v3-test"

    # Non-empty identifier (falls back to the deterministic name).
    assert returned == "crucible-world_1-v3-test"


def test_log_experiment_prefers_server_name(monkeypatch, eval_result):
    sink = _install_fake_client(monkeypatch)

    # Override run_experiment to return an object exposing a server name.
    def run_experiment(**kwargs):
        sink["experiment"] = kwargs
        obj = pytypes.SimpleNamespace(name="server-assigned-123")
        return obj

    sink_client = sys.modules["phoenix.client"]
    original = sink_client.Client

    def patched(**kwargs):
        client = original(**kwargs)
        client.experiments.run_experiment = run_experiment
        return client

    monkeypatch.setattr(sink_client, "Client", patched)

    returned = phoenix_client.log_experiment(eval_result, db_id="world_1")

    assert returned == "server-assigned-123"


def test_log_experiment_task_and_evaluator_behaviour(monkeypatch, eval_result):
    """The task echoes stored predictions; the evaluator maps is_match -> score."""
    sink = _install_fake_client(monkeypatch)

    phoenix_client.log_experiment(eval_result, db_id="world_1")

    exp = sink["experiment"]
    task = exp["task"]
    evaluator = exp["evaluators"][0]

    match_meta = sink["dataset"]["metadata"][0]
    out = task(match_meta)
    assert out == {
        "predicted_sql": "SELECT count(*) FROM t",
        "is_match": True,
        "error": None,
    }
    assert evaluator(out) == 1.0

    miss_meta = sink["dataset"]["metadata"][1]
    assert evaluator(task(miss_meta)) == 0.0


# --- promote_prompt ----------------------------------------------------------


def test_promote_prompt_builds_chat_messages(monkeypatch):
    sink = _install_fake_client(monkeypatch)
    _install_fake_prompt_types(monkeypatch, sink)
    monkeypatch.setenv("GEMINI_MODEL", "gemini-test")

    phoenix_client.promote_prompt(
        name="winner",
        system_prompt="You are an analyst.",
        few_shots=(("q1", "SELECT 1"), ("q2", "SELECT 2")),
    )

    pv = sink["prompt_version"]
    assert pv.model_name == "gemini-test"
    assert pv.messages == [
        {"role": "system", "content": "You are an analyst."},
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": "SELECT 1"},
        {"role": "user", "content": "q2"},
        {"role": "assistant", "content": "SELECT 2"},
    ]

    create = sink["prompt"]
    assert create["name"] == "winner"
    assert create["version"] is pv


def test_promote_prompt_defaults_model(monkeypatch):
    sink = _install_fake_client(monkeypatch)
    _install_fake_prompt_types(monkeypatch, sink)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)

    phoenix_client.promote_prompt("w", "sys", few_shots=())

    assert sink["prompt_version"].model_name == phoenix_client._DEFAULT_MODEL
    assert sink["prompt_version"].messages == [{"role": "system", "content": "sys"}]
