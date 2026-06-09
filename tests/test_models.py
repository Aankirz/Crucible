"""Unit tests for the Gemini model adapter (crucible.models).

All tests are deterministic and offline: `genai.Client` is monkeypatched with a
fake, `time.sleep` is patched to a no-op so retries are instant, and the API key
is injected via env. No network or real credentials are touched.
"""
from __future__ import annotations

import pytest

from crucible import models
from crucible.models import _retry_delay_seconds


class _FakeResponse:
    """Mimics the SDK response object: only `.text` is read by the adapter."""

    def __init__(self, text):
        self.text = text


class _FakeModels:
    """Stands in for `client.models`; scripts a sequence of return/raise actions."""

    def __init__(self, actions):
        self._actions = list(actions)
        self.calls = []

    def generate_content(self, *, model, contents, config):
        self.calls.append({"model": model, "contents": contents, "config": config})
        action = self._actions.pop(0)
        if isinstance(action, Exception):
            raise action
        return action


class _FakeClient:
    """Stands in for `genai.Client`; exposes a `.models` with scripted actions."""

    def __init__(self, actions):
        self.models = _FakeModels(actions)


def _client_error(code, body=None):
    """Build a real genai ClientError with the given HTTP status code."""
    payload = body or {"error": {"message": "boom", "status": "X"}}
    return models.genai_errors.ClientError(code, payload)


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    """Make retry backoff instantaneous for every test in this module."""
    monkeypatch.setattr(models.time, "sleep", lambda *_: None)


@pytest.fixture
def _api_key(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    monkeypatch.delenv("GEMINI_MODEL", raising=False)


def _install_client(monkeypatch, actions):
    """Patch genai.Client so building the model uses our fake; return the fake."""
    captured = {}

    def factory(*, api_key):
        captured["api_key"] = api_key
        client = _FakeClient(actions)
        captured["client"] = client
        return client

    monkeypatch.setattr(models.genai, "Client", factory)
    return captured


def test_returns_model_text_on_success(_api_key, monkeypatch):
    captured = _install_client(monkeypatch, [_FakeResponse("SELECT 1;")])

    fn = models.gemini_model()
    out = fn("write some sql")

    assert out == "SELECT 1;"
    assert captured["api_key"] == "test-key"
    # Defaults: model id and temperature-0 config wired through.
    call = captured["client"].models.calls[0]
    assert call["model"] == models.DEFAULT_MODEL
    assert call["contents"] == "write some sql"
    assert call["config"].temperature == models.SCORING_TEMPERATURE


def test_explicit_model_name_overrides_default(_api_key, monkeypatch):
    captured = _install_client(monkeypatch, [_FakeResponse("ok")])

    fn = models.gemini_model("gemini-custom")
    fn("q")

    assert captured["client"].models.calls[0]["model"] == "gemini-custom"


def test_env_model_name_used_when_no_argument(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "k")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-from-env")
    captured = _install_client(monkeypatch, [_FakeResponse("ok")])

    fn = models.gemini_model()
    fn("q")

    assert captured["client"].models.calls[0]["model"] == "gemini-from-env"


def test_raises_runtime_error_when_api_key_missing(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="GOOGLE_API_KEY"):
        models.gemini_model()


def test_none_text_returns_empty_string(_api_key, monkeypatch):
    _install_client(monkeypatch, [_FakeResponse(None)])

    fn = models.gemini_model()

    assert fn("q") == ""


def test_retries_on_429_then_succeeds(_api_key, monkeypatch):
    actions = [_client_error(429), _FakeResponse("recovered")]
    captured = _install_client(monkeypatch, actions)

    fn = models.gemini_model()
    out = fn("q")

    assert out == "recovered"
    # One failed attempt + one successful attempt.
    assert len(captured["client"].models.calls) == 2


def test_retries_on_503_then_succeeds(_api_key, monkeypatch):
    # 503 ServerError is also retryable.
    err = models.genai_errors.ServerError(503, {"error": {"message": "overloaded"}})
    captured = _install_client(monkeypatch, [err, _FakeResponse("ok")])

    fn = models.gemini_model()

    assert fn("q") == "ok"
    assert len(captured["client"].models.calls) == 2


def test_non_retryable_code_reraised_immediately(_api_key, monkeypatch):
    captured = _install_client(monkeypatch, [_client_error(400)])

    fn = models.gemini_model()

    with pytest.raises(models.genai_errors.ClientError):
        fn("q")
    # No retry: only the single failing attempt.
    assert len(captured["client"].models.calls) == 1


def test_gives_up_after_max_retries(_api_key, monkeypatch):
    actions = [_client_error(429) for _ in range(models.MAX_RETRIES)]
    captured = _install_client(monkeypatch, actions)

    fn = models.gemini_model()

    with pytest.raises(models.genai_errors.ClientError):
        fn("q")
    assert len(captured["client"].models.calls) == models.MAX_RETRIES


# --- _retry_delay_seconds ----------------------------------------------------


def test_retry_delay_parses_structured_field():
    err = Exception("429 RESOURCE_EXHAUSTED {'retryDelay': '33s'}")
    # Server hint + 1.0s safety margin.
    assert _retry_delay_seconds(err, attempt=0) == 34.0


def test_retry_delay_parses_prose_message():
    err = Exception("Quota exceeded. Please retry in 9.3s")
    assert _retry_delay_seconds(err, attempt=0) == pytest.approx(10.3)


def test_retry_delay_falls_back_to_exponential():
    err = Exception("some opaque error with no hint")
    assert _retry_delay_seconds(err, attempt=0) == models.DEFAULT_BACKOFF_S
    assert _retry_delay_seconds(err, attempt=2) == models.DEFAULT_BACKOFF_S * 4
