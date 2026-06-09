"""Production Gemini adapter: builds a `ModelFn` backed by Google's Gemini.

Wraps the `google-genai` SDK behind the project's single LLM seam (`ModelFn` from
`crucible.types`). The returned closure runs at temperature 0 so candidate scoring
is deterministic and reproducible across runs.

API shape verified against the current google-genai SDK README
(github.com/googleapis/python-genai, SDK v2.x) on 2026-06-08:
  - import:  `from google import genai` / `from google.genai import types`
  - client:  `genai.Client(api_key=...)`
  - call:    `client.models.generate_content(model=..., contents=...,
               config=types.GenerateContentConfig(temperature=0.0))`
  - text:    `response.text` (may be None when there are no candidates/parts)

Confirmed live (2026-06-09): `gemini-3-flash-preview` works on the free tier and
returns SQL; the pro models return 429 with free-tier limit 0 (need billing). The
adapter retries 429s with backoff so the multi-call loop survives throttling.
"""
from __future__ import annotations

import os
import re
import time

from google import genai
from google.genai import types
from google.genai import errors as genai_errors

from crucible.types import ModelFn

# Free-tier default: a real, available Gemini 3 model id. The pro models require
# billing (free-tier limit is 0), so flash is the safe default for the loop.
DEFAULT_MODEL = "gemini-3-flash-preview"
# Temperature 0 -> greedy decoding for deterministic, reproducible scoring.
SCORING_TEMPERATURE = 0.0
# The loop makes many calls; free tiers throttle. Retry 429s with backoff so a
# rate limit pauses the run instead of crashing it.
MAX_RETRIES = 6
DEFAULT_BACKOFF_S = 8.0
# Transient HTTP codes worth retrying: 429 rate limit, 503 model overloaded.
RETRYABLE_CODES = (429, 503)


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in ("1", "true", "yes", "on")


def _build_client() -> "genai.Client":
    """Build a genai client in one of two modes:

    * **Vertex AI** (when `GOOGLE_GENAI_USE_VERTEXAI` is truthy): authenticates via
      Application Default Credentials (`gcloud auth application-default login`) and
      bills the Cloud project — so Google Cloud credits ($300 trial / lab credits)
      are consumed instead of the AI-Studio free tier. Requires `GOOGLE_CLOUD_PROJECT`
      and `GOOGLE_CLOUD_LOCATION` (e.g. `us-central1`).
    * **AI Studio** (default): authenticates with the `GOOGLE_API_KEY` API key.
    """
    if _truthy(os.environ.get("GOOGLE_GENAI_USE_VERTEXAI")):
        project = os.environ.get("GOOGLE_CLOUD_PROJECT")
        location = os.environ.get("GOOGLE_CLOUD_LOCATION")
        if not project or not location:
            raise RuntimeError(
                "Vertex mode needs GOOGLE_CLOUD_PROJECT and GOOGLE_CLOUD_LOCATION "
                "(and `gcloud auth application-default login`)."
            )
        return genai.Client(vertexai=True, project=project, location=location)

    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GOOGLE_API_KEY is not set; required for AI-Studio mode. "
            "(Or set GOOGLE_GENAI_USE_VERTEXAI=true to use Vertex AI + Cloud credits.)"
        )
    return genai.Client(api_key=api_key)


def gemini_model(model_name: str | None = None) -> ModelFn:
    """Build a `ModelFn` backed by Gemini via the google-genai SDK.

    Auth mode is chosen by `_build_client`: Vertex AI (Cloud credits) when
    `GOOGLE_GENAI_USE_VERTEXAI` is truthy, else AI Studio via `GOOGLE_API_KEY`.
    The model name resolves from `model_name`, then `GEMINI_MODEL`, then `DEFAULT_MODEL`.

    Args:
        model_name: Optional explicit model id. Overrides the env var when given.

    Returns:
        A closure `(prompt: str) -> str` that calls Gemini at temperature 0 and
        returns the response text (empty string when the response has no text).

    Raises:
        RuntimeError: If required auth env vars for the selected mode are missing.
    """
    resolved_model = model_name or os.environ.get("GEMINI_MODEL") or DEFAULT_MODEL

    client = _build_client()
    config = types.GenerateContentConfig(temperature=SCORING_TEMPERATURE)

    def call(prompt: str) -> str:
        """Send `prompt` to Gemini and return the raw response text.

        Retries transient failures with backoff so the multi-call loop pauses
        rather than crashes: 429 (rate limit, honoring the server's suggested
        delay) and 503 (model temporarily overloaded).
        """
        for attempt in range(MAX_RETRIES):
            try:
                response = client.models.generate_content(
                    model=resolved_model,
                    contents=prompt,
                    config=config,
                )
                return response.text or ""
            except (genai_errors.ClientError, genai_errors.ServerError) as e:
                if getattr(e, "code", None) not in RETRYABLE_CODES \
                        or attempt == MAX_RETRIES - 1:
                    raise
                time.sleep(_retry_delay_seconds(e, attempt))
        return ""

    return call


def _retry_delay_seconds(error: Exception, attempt: int) -> float:
    """Backoff for a 429: prefer the server's suggested delay, else exponential.

    Matches both the structured `'retryDelay': '33s'` field and the prose
    `Please retry in 33.7s` message that the Gemini API returns.
    """
    text = str(error)
    match = re.search(r"retry\s*[dD]elay['\"]?:?\s*['\"]?(\d+(?:\.\d+)?)", text) \
        or re.search(r"retry in\s*(\d+(?:\.\d+)?)\s*s", text)
    if match:
        return float(match.group(1)) + 1.0
    return DEFAULT_BACKOFF_S * (2 ** attempt)
