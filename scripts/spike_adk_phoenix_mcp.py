"""Wiring spike: confirm the live ADK <-> Phoenix <-> MCP integration.

This is a throwaway, manual-confirmation script (no test). It de-risks the
single riskiest integration in the project BEFORE the orchestrator relies on it:

  (a) Google ADK + Gemini actually runs an agent turn,
  (b) OpenTelemetry traces land in Phoenix Cloud (via ``init_tracing``),
  (c) the Arize Phoenix MCP server is reachable as an ADK ``McpToolset`` and the
      agent can call its tools to introspect the Phoenix space.

It mirrors the toolset/agent construction in ``crucible.mcp_introspect`` exactly
so that whatever this spike proves working is the same wiring the loop depends on.
If any import path or MCP flag differs against the installed ADK / phoenix-mcp,
fix it HERE first, then mirror the fix into ``crucible.mcp_introspect``.

Run: ``make spike``   (requires a populated .env with PHOENIX_* + GOOGLE_* keys)

Expected: the agent prints the projects/experiments in the Phoenix space, then
``SPIKE OK``; a trace for this run appears in the Phoenix UI under the configured
project.

API shapes (verified against google-adk 2.x + the Arize gemini-hackathon
``.gemini/settings.json``; see crucible/mcp_introspect.py for the full notes):
  * ``from google.adk.agents import LlmAgent``
  * ``from google.adk.tools.mcp_tool import McpToolset, StdioConnectionParams``
  * ``from mcp import StdioServerParameters``
  * ``Runner(app_name=, agent=, session_service=)`` + ``InMemorySessionService``
  * ``runner.run_async(*, user_id=, session_id=, new_message=)`` (keyword-only)
  * phoenix-mcp launch: ``npx -y @arizeai/phoenix-mcp@latest --baseUrl <ep> --apiKey <key>``

Fallback if the ADK MCPToolset path is unworkable from real creds: run the
Phoenix MCP server inside a Gemini-CLI subprocess (see the fallback note in
``crucible.mcp_introspect``) and have introspection shell out to it. The rest of
the project depends only on ``introspect_failures(name) -> str``, not on transport.
"""
from __future__ import annotations

import asyncio
import os

from dotenv import load_dotenv

load_dotenv()

# (b) Phoenix tracing — reuse the project's single tracing entry point so the
# spike exercises the exact registration the rest of the system uses.
from crucible.phoenix_client import init_tracing

# Phoenix MCP server is a Node package launched via npx (stdio transport). Keep
# this identical to crucible.mcp_introspect._PHOENIX_MCP_PACKAGE.
PHOENIX_MCP_PACKAGE = "@arizeai/phoenix-mcp@latest"

# Give the npx stdio server room to cold-start (npx may download the package).
MCP_CONNECT_TIMEOUT_SECONDS = 30.0

APP_NAME = "crucible_spike"
USER_ID = "dev"
SESSION_ID = "spike"

SPIKE_PROMPT = (
    "Using the Arize Phoenix MCP tools, list the projects and experiments in my "
    "Phoenix space. Be terse: just enumerate what you find."
)


def _build_phoenix_toolset():
    """Construct the Phoenix MCP toolset (stdio via npx).

    Mirrors ``crucible.mcp_introspect._build_phoenix_toolset``. Imports are lazy
    so importing this module never hard-requires google-adk / mcp.

    Returns:
        An ``McpToolset`` instance whose lifecycle the caller must close.
    """
    from google.adk.tools.mcp_tool import McpToolset, StdioConnectionParams
    from mcp import StdioServerParameters

    base_url = os.environ["PHOENIX_COLLECTOR_ENDPOINT"]
    api_key = os.environ["PHOENIX_API_KEY"]

    server_params = StdioServerParameters(
        command="npx",
        # API key passed ONLY via env (below), never argv (argv leaks via `ps`).
        args=[
            "-y",
            PHOENIX_MCP_PACKAGE,
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
            timeout=MCP_CONNECT_TIMEOUT_SECONDS,
        )
    )


def _extract_text(event) -> str:
    """Pull any model text out of an ADK event, tolerating missing fields."""
    content = getattr(event, "content", None)
    parts = getattr(content, "parts", None) or []
    return "".join(getattr(part, "text", "") or "" for part in parts)


async def _run_spike_async() -> str:
    """Build the ADK agent + Phoenix toolset, run one turn, return text output."""
    from google.adk.agents import LlmAgent
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types

    model = os.environ.get("GEMINI_MODEL", "gemini-3-pro")
    toolset = _build_phoenix_toolset()
    try:
        agent = LlmAgent(
            model=model,
            name="crucible_spike_agent",
            instruction=(
                "You can introspect Arize Phoenix via the attached MCP tools. "
                "Be terse and factual."
            ),
            tools=[toolset],
        )

        session_service = InMemorySessionService()
        await session_service.create_session(
            app_name=APP_NAME,
            user_id=USER_ID,
            session_id=SESSION_ID,
            state={},
        )
        runner = Runner(
            app_name=APP_NAME,
            agent=agent,
            session_service=session_service,
        )

        message = types.Content(
            role="user",
            parts=[types.Part(text=SPIKE_PROMPT)],
        )

        chunks: list[str] = []
        async for event in runner.run_async(
            user_id=USER_ID,
            session_id=SESSION_ID,
            new_message=message,
        ):
            chunks.append(_extract_text(event))

        return "".join(chunks).strip()
    finally:
        # Always tear down the npx subprocess / stdio connection.
        await toolset.close()


def main() -> None:
    """Run the wiring spike end-to-end and print the result + ``SPIKE OK``."""
    # (b) Register tracing first so the agent turn below is captured in Phoenix.
    init_tracing()

    # (a) + (c) Run a single agent turn that exercises the Phoenix MCP toolset.
    output = asyncio.run(_run_spike_async())
    print(output)
    print("SPIKE OK")


if __name__ == "__main__":
    main()
