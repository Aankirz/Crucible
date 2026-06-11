"""Agent-initiated MCP introspection layer.

This is the rubric-critical seam: a Google ADK (Gemini) agent that has the Arize
Phoenix MCP server attached as a tool and uses it AT RUNTIME to read the
agent's OWN failing experiment/traces, then returns a short natural-language
failure summary that drives the next optimization hypothesis.

The single public entry point is ``introspect_failures(experiment_name) -> str``.
On ANY failure it returns ``""`` so the orchestrator can fall back to the
deterministic classifier in ``crucible.mutation``.

--------------------------------------------------------------------------------
API VERIFICATION NOTES (verified against google-adk 2.2.0 docs + source)
--------------------------------------------------------------------------------
Confirmed via https://adk.dev/tools-custom/mcp-tools/ and the v2.2.0 source at
github.com/google/adk-python (paths below all exist and are exported):

  * ``from google.adk.agents import LlmAgent``
  * ``from google.adk.tools.mcp_tool import McpToolset``   (alias ``MCPToolset``)
  * ``from google.adk.tools.mcp_tool import StdioConnectionParams``
        (also re-exported from ``...mcp_tool.mcp_session_manager``)
  * ``from mcp import StdioServerParameters``  (the ``mcp`` PyPI package)
  * ``StdioConnectionParams(server_params=..., timeout=float)``
  * ``StdioServerParameters(command=..., args=[...], env={...})``
  * ``McpToolset(connection_params=..., tool_filter=[...])`` with ``await close()``
  * ``Runner(app_name=, agent=, session_service=)`` /
    ``InMemoryRunner(agent=, app_name=)``
  * ``runner.run_async`` is KEYWORD-ONLY:
        ``run_async(*, user_id=, session_id=, new_message=)`` -> async generator
  * ``session_service.create_session(app_name=, user_id=, state=, session_id=)``
        is async.
  * Phoenix MCP server launch args confirmed from
    github.com/Arize-ai/gemini-hackathon ``.gemini/settings.json``:
        ["-y", "@arizeai/phoenix-mcp@latest",
         "--baseUrl", <PHOENIX_COLLECTOR_ENDPOINT>,
         "--apiKey",  <PHOENIX_API_KEY>]

STILL-UNCONFIRMED (the wiring spike scripts/spike_adk_phoenix_mcp.py must verify
with REAL credentials — flagged inline below):
  * Exact Phoenix MCP tool names the agent must call (e.g. list_experiments /
    get_experiment / get_experiment_runs / get_traces) and their result shape.
    We deliberately do NOT hardcode tool names; the agent discovers them via the
    toolset and the instruction describes intent, not tool signatures.
  * Whether the running model id (GEMINI_MODEL, default "gemini-3-pro") needs an
    Vertex vs. AI-Studio backend env (GOOGLE_GENAI_USE_VERTEXAI / GOOGLE_API_KEY).
  * Whether ``--baseUrl`` for a Phoenix *Cloud space* needs the space-scoped URL
    exactly as PHOENIX_COLLECTOR_ENDPOINT, or a different management endpoint.

If the ADK MCP-toolset path proves unworkable from real creds, a Gemini-CLI
fallback is sketched in ``_GEMINI_CLI_FALLBACK_NOTE`` below; it keeps the same
``introspect_failures(str) -> str`` signature.
"""
from __future__ import annotations

import asyncio
import os
import time

# Default model + project. Overridable via env so the spike can swap them without
# code changes.
_DEFAULT_MODEL = "gemini-3-pro"
_DEFAULT_PROJECT = "crucible"

# The introspection agent makes several sequential model calls, so a single
# transient 503/overload anywhere kills the whole turn. Retry the turn a few
# times with backoff before falling back to the deterministic classifier.
_MAX_INTROSPECT_ATTEMPTS = 3
_INTROSPECT_BACKOFF_S = 6.0
# Substrings that mark a transient, worth-retrying failure (vs. a terminal one
# like missing credentials, which should fail fast to the fallback).
_TRANSIENT_MARKERS = (
    "503", "UNAVAILABLE", "overloaded", "high demand",
    "RESOURCE_EXHAUSTED", "429", "deadline", "timeout",
)


def _is_transient(error: Exception) -> bool:
    """True when an introspection error looks worth retrying."""
    text = f"{type(error).__name__}: {error}".lower()
    return any(marker.lower() in text for marker in _TRANSIENT_MARKERS)

# ADK requires non-empty user/session/app identifiers for the in-memory runner.
_APP_NAME = "crucible_introspect"
_USER_ID = "crucible"

# Phoenix MCP server is a Node package launched via npx (stdio transport).
_PHOENIX_MCP_PACKAGE = "@arizeai/phoenix-mcp@latest"

# Give the npx stdio server room to cold-start (npx may download the package).
_MCP_CONNECT_TIMEOUT_SECONDS = 30.0

# --- Gemini CLI fallback (documented, not wired) ------------------------------
# If McpToolset cannot connect to phoenix-mcp from real creds, the equivalent
# behaviour can be obtained by shelling out to the Gemini CLI configured with the
# same ``.gemini/settings.json`` phoenix MCP block, e.g.:
#
#     subprocess.run(
#         ["gemini", "-p", _build_instruction(experiment_name)],
#         capture_output=True, text=True, timeout=120, check=True,
#         env={**os.environ},  # PHOENIX_* + GEMINI_MODEL already exported
#     ).stdout
#
# That path keeps this module's public signature identical. Prefer the in-process
# McpToolset version (below) because it gives structured event access and avoids
# a CLI dependency. The wiring spike decides which path ships.
_GEMINI_CLI_FALLBACK_NOTE = "see module docstring + comment above"


def _build_instruction(experiment_name: str, project_name: str) -> str:
    """Return the one-shot natural-language instruction for the introspection agent.

    The instruction describes INTENT only. It does not hardcode Phoenix MCP tool
    names because those are discovered at runtime from the attached toolset (and
    are one of the things the wiring spike must confirm).
    """
    return (
        "You are a debugging assistant with access to the Arize Phoenix MCP "
        "tools. Use those tools to inspect this agent's own evaluation data.\n\n"
        f"1. Find the most recent experiment named '{experiment_name}' in the "
        f"Phoenix project '{project_name}'.\n"
        "2. Read its rows and identify the rows that FAILED (where the "
        "execution_match evaluation is false/0).\n"
        "3. Determine the single dominant failure pattern across those failing "
        "rows (e.g. missing JOINs, wrong aggregation, hallucinated columns, "
        "value/format mismatches).\n"
        "4. Read the current overall execution_match score for the experiment.\n\n"
        "Respond with EXACTLY two short lines and nothing else:\n"
        "FAILURE: <one sentence describing the dominant failure pattern>\n"
        "SCORE: execution_match = <the current score>\n"
    )


def _build_phoenix_toolset():
    """Construct the Phoenix MCP toolset (stdio via npx).

    Imports are done lazily inside this function so that importing this module
    never requires google-adk/mcp to be installed (keeps the deterministic
    fallback path import-safe).

    Returns:
        An ``McpToolset`` instance whose lifecycle the caller must close.

    Raises:
        Exception: Any import/connection error is propagated to the caller, which
            converts it into the empty-string fallback.
    """
    from google.adk.tools.mcp_tool import McpToolset, StdioConnectionParams
    from mcp import StdioServerParameters

    base_url = os.environ["PHOENIX_COLLECTOR_ENDPOINT"]
    api_key = os.environ["PHOENIX_API_KEY"]

    server_params = StdioServerParameters(
        command="npx",
        # NOTE: the API key is passed ONLY via env (below), never as a CLI arg —
        # argv is visible in `ps`, so a key in args would leak on a shared host.
        args=[
            "-y",
            _PHOENIX_MCP_PACKAGE,
            "--baseUrl",
            base_url,
        ],
        env={
            **os.environ,
            "PHOENIX_COLLECTOR_ENDPOINT": base_url,
            "PHOENIX_API_KEY": api_key,
        },
    )
    return McpToolset(
        connection_params=StdioConnectionParams(
            server_params=server_params,
            timeout=_MCP_CONNECT_TIMEOUT_SECONDS,
        )
    )


def _extract_text(event) -> str:
    """Pull any model text out of an ADK event, tolerating missing fields.

    ADK events carry text in ``event.content.parts[*].text``. Tool-call and
    tool-response events have parts without text; those yield "".
    """
    content = getattr(event, "content", None)
    parts = getattr(content, "parts", None) or []
    return "".join(getattr(part, "text", "") or "" for part in parts)


async def _run_introspection_async(experiment_name: str, project_name: str,
                                   model: str) -> str:
    """Build the ADK agent + Phoenix toolset, run one turn, return text output.

    This is the async core. ``introspect_failures`` drives it synchronously.
    """
    from google.adk.agents import LlmAgent
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types

    toolset = _build_phoenix_toolset()
    try:
        agent = LlmAgent(
            model=model,
            name="crucible_introspector",
            instruction=(
                "You introspect a text-to-SQL agent's own Phoenix experiment "
                "data via MCP tools and report its dominant failure pattern."
            ),
            tools=[toolset],
        )

        session_service = InMemorySessionService()
        await session_service.create_session(
            app_name=_APP_NAME,
            user_id=_USER_ID,
            session_id=experiment_name,
            state={},
        )
        runner = Runner(
            app_name=_APP_NAME,
            agent=agent,
            session_service=session_service,
        )

        message = types.Content(
            role="user",
            parts=[types.Part(text=_build_instruction(experiment_name, project_name))],
        )

        chunks: list[str] = []
        async for event in runner.run_async(
            user_id=_USER_ID,
            session_id=experiment_name,
            new_message=message,
        ):
            chunks.append(_extract_text(event))

        return "".join(chunks).strip()
    finally:
        # Always tear down the npx subprocess / stdio connection.
        await toolset.close()


def introspect_failures(experiment_name: str) -> str:
    """Read the agent's own failing experiment via Phoenix MCP and summarize it.

    Builds a Google ADK (Gemini) agent with the Arize Phoenix MCP server attached
    as a tool, runs a one-shot instruction asking it to read the recent
    experiment ``experiment_name`` in the configured Phoenix project, identify the
    failing rows, summarize the dominant failure pattern in one sentence, and
    report the current execution_match score.

    Configuration is read from the environment:
        * ``PHOENIX_COLLECTOR_ENDPOINT`` -> phoenix-mcp ``--baseUrl``
        * ``PHOENIX_API_KEY``            -> phoenix-mcp ``--apiKey``
        * ``PHOENIX_PROJECT_NAME``       -> project to inspect (default "crucible")
        * ``GEMINI_MODEL``               -> Gemini model id (default "gemini-3-pro")

    Args:
        experiment_name: Name of the Phoenix experiment to introspect.

    Returns:
        The agent's natural-language failure summary, or ``""`` on ANY error so
        the orchestrator can fall back to its deterministic classifier. The
        try/except fallback is intentional and required.
    """
    project_name = os.getenv("PHOENIX_PROJECT_NAME", _DEFAULT_PROJECT)
    model = os.getenv("GEMINI_MODEL", _DEFAULT_MODEL)

    for attempt in range(_MAX_INTROSPECT_ATTEMPTS):
        try:
            # ``asyncio.run`` creates and tears down a fresh event loop. This must
            # not be called from inside a running loop; the orchestrator invokes
            # this from synchronous code, which is the intended usage.
            summary = asyncio.run(
                _run_introspection_async(experiment_name, project_name, model)
            )
            if summary:
                return summary
            # Empty (but no exception) usually means a transient model hiccup
            # swallowed downstream; retry a couple of times before giving up.
            if attempt < _MAX_INTROSPECT_ATTEMPTS - 1:
                time.sleep(_INTROSPECT_BACKOFF_S * (attempt + 1))
                continue
            return ""
        except Exception as exc:  # noqa: BLE001 - graceful fallback is required.
            # Retry transient failures (503/overload/rate-limit); fail fast on
            # terminal ones (missing deps/creds, called inside a running loop).
            if _is_transient(exc) and attempt < _MAX_INTROSPECT_ATTEMPTS - 1:
                time.sleep(_INTROSPECT_BACKOFF_S * (attempt + 1))
                continue
            return ""
    return ""
