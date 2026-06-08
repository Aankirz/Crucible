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

Unconfirmed without a live key (verify at e2e):
  - The default model name "gemini-3-pro" is taken from the task spec; confirm it
    is a valid, available model id for the target API tier (README examples use
    gemini-2.5-flash / gemini-3.x ids). Override via `model_name` arg or the
    `GEMINI_MODEL` env var if the call rejects it.
  - Exact behavior of `response.text` when the response is blocked by safety
    filters (we coalesce any falsy value to "").
"""
from __future__ import annotations

import os

from google import genai
from google.genai import types

from crucible.types import ModelFn

DEFAULT_MODEL = "gemini-3-pro"
# Temperature 0 -> greedy decoding for deterministic, reproducible scoring.
SCORING_TEMPERATURE = 0.0


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
        """Send `prompt` to Gemini and return the raw response text."""
        response = client.models.generate_content(
            model=resolved_model,
            contents=prompt,
            config=config,
        )
        return response.text or ""

    return call
