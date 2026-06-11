"""Pytest-wide isolation from a developer's local `.env`.

`crucible.server.app` calls `load_dotenv()` at import time. On a developer machine
the repo `.env` may enable Vertex AI mode (`GOOGLE_GENAI_USE_VERTEXAI=true`) to
draw cloud credits. That value would otherwise leak into the test process the
moment `test_server` imports the app, sending `crucible.models` down the Vertex
client path and breaking the API-key-based `test_models` fakes (a test-ordering
flake, not a product bug).

Neutralizing these credential/mode vars BEFORE any test module imports keeps the
suite deterministic and identical to a clean CI environment. We set them to an
empty string (rather than deleting them) so that `app.py`'s import-time
`load_dotenv()` — which uses the default `override=False` — will NOT re-populate
them from the repo `.env`. `crucible.models._truthy("")` is False, so the empty
value selects the API-key path the test fakes expect.

Production is unaffected: the real deployment sets these in the host environment,
not via this test-only fixture.
"""
from __future__ import annotations

import os

# Vertex/AI-Studio selection + cloud-credential vars that must not influence the
# deterministic, offline test suite if present in a local `.env`.
_LEAKY_ENV_VARS = (
    "GOOGLE_GENAI_USE_VERTEXAI",
    "GOOGLE_CLOUD_PROJECT",
    "GOOGLE_CLOUD_LOCATION",
)

# Set (not delete) to empty so a later load_dotenv(override=False) cannot re-add them.
for _var in _LEAKY_ENV_VARS:
    os.environ[_var] = ""
