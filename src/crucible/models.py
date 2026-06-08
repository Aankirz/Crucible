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
MAX_RETRIES = 5
DEFAULT_BACKOFF_S = 8.0


def gemini_model(model_name: str | None = None) -> ModelFn:
    """Build a `ModelFn` backed by Gemini via the google-genai SDK.

    The API key is read from the `GOOGLE_API_KEY` environment variable. The model
    name is resolved from the `model_name` argument, then the `GEMINI_MODEL`
    environment variable, then `DEFAULT_MODEL`.

    Args:
        model_name: Optional explicit model id. Overrides the env var when given.

    Returns:
        A closure `(prompt: str) -> str` that calls Gemini at temperature 0 and
        returns the response text (empty string when the response has no text).

    Raises:
        RuntimeError: If `GOOGLE_API_KEY` is not set in the environment.
    """
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GOOGLE_API_KEY is not set; required to build the Gemini model adapter."
        )

    resolved_model = model_name or os.environ.get("GEMINI_MODEL") or DEFAULT_MODEL

    client = genai.Client(api_key=api_key)
    config = types.GenerateContentConfig(temperature=SCORING_TEMPERATURE)

    def call(prompt: str) -> str:
        """Send `prompt` to Gemini and return the raw response text.

        Retries on 429 (rate limit), honoring the server's suggested retry delay
        when present, so a throttled free tier pauses rather than crashes the loop.
        """
        for attempt in range(MAX_RETRIES):
            try:
                response = client.models.generate_content(
                    model=resolved_model,
                    contents=prompt,
                    config=config,
                )
                return response.text or ""
            except genai_errors.ClientError as e:
                if getattr(e, "code", None) != 429 or attempt == MAX_RETRIES - 1:
                    raise
                time.sleep(_retry_delay_seconds(e, attempt))
        return ""

    return call


def _retry_delay_seconds(error: Exception, attempt: int) -> float:
    """Backoff for a 429: prefer the server's suggested 'retryDelay', else exponential."""
    match = re.search(r"ret[dD]elay['\"]?:\s*['\"]?(\d+(?:\.\d+)?)", str(error))
    if match:
        return float(match.group(1)) + 1.0
    return DEFAULT_BACKOFF_S * (2 ** attempt)
