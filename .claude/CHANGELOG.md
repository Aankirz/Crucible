# Crucible — Changelog

## 2026-06-07 — Design spec locked
- Ran a full grilling session resolving the design tree (track, concept, demo task, optimizer, eval design, MCP integration, runtime, UI, deployment, build order).
- Created `docs/superpowers/specs/2026-06-07-crucible-design.md` capturing the locked design for the Arize-track "Crucible" agent (an agent that builds & self-optimizes text-to-SQL agents, improving via its own Phoenix traces through the Phoenix MCP server).
- Initialized git repo on branch `design/crucible-spec`.

## 2026-06-07 — Implementation plan written
- Created `docs/superpowers/plans/2026-06-07-crucible.md`: full TDD, bite-sized implementation plan across 8 phases (scaffold+spike → deterministic core → dataset pipeline → candidate/eval → Phoenix+MCP → mutation → orchestrator loop → Mission Control UI → pre-baked/Cloud Run/demo). Includes spec-coverage self-review.

## 2026-06-07 — PRD written (saved locally)
- Created `docs/superpowers/prds/2026-06-07-crucible.md` via /to-prd: problem/solution, 31 user stories, implementation + testing decisions (confirmed seams: ModelFn + run_loop callbacks + real sandbox), out-of-scope, notes. Marked ready-for-agent. No tracker configured, so saved locally instead of publishing an issue.

## 2026-06-07 — Published to GitHub
- Connected remote Aankirz/Crucible; rebased planning docs onto the LICENSE base.
- Merged design baseline (spec + plan + PRD) to `main` via PR #1.
- Created `ready-for-agent` label; published the PRD as issue #2 with that label.

## 2026-06-08 — GATE 0 foundation + two-team coordination
- Built foundation: pyproject.toml, Makefile, .env.example, package layout, `src/crucible/types.py` (shared contract incl. ModelFn + Hypothesis), `src/crucible/server/events.py` (frozen SSE event contract). Verified contracts import cleanly.
- Added `docs/superpowers/COORDINATION.md` (gates + disjoint file ownership + merge protocol).
- Added per-team session plans with explicit STOP/coordinate markers: `SESSION-TEAM-A.md` (eval substrate, credential-free) and `SESSION-TEAM-B.md` (brain + integration).
- Added `MASTER-PROJECT-PLAN.md` as the private PM command center — git-ignored (added to .gitignore).

## 2026-06-08 — [Team B] mutation engine (5.1 + 5.2)
- Added `src/crucible/mutation.py`: failure classification (fixed taxonomy), top-cluster pick, model-driven mutation proposal, and immutable hypothesis application. TDD, 6/6 tests green.

## 2026-06-08 — Gemini model adapter
- Added `src/crucible/models.py`: `gemini_model(model_name=None) -> ModelFn`, the production Gemini adapter backed by the `google-genai` SDK. Reads `GOOGLE_API_KEY`, resolves model from arg/`GEMINI_MODEL`/default `gemini-3-pro`, returns a closure that calls Gemini at temperature 0.0 for deterministic scoring. API shape verified against the current google-genai SDK README (v2.x).

## 2026-06-08 — Add phoenix_client.py
- Created src/crucible/phoenix_client.py: thin Arize Phoenix plumbing for OTel tracing registration (init_tracing), logging a scored EvalResult as a Phoenix experiment (log_experiment), and promoting a winning prompt to the prompt registry (promote_prompt). API verified against arize-phoenix-otel 0.13.0 / arize-phoenix-client 2.7.0 docs.

## 2026-06-08 — Agent-initiated MCP introspection layer
- Created `src/crucible/mcp_introspect.py` implementing `introspect_failures(experiment_name: str) -> str`: builds a Google ADK (Gemini) agent with the Arize Phoenix MCP server (`@arizeai/phoenix-mcp@latest` via npx, stdio) attached as a tool, runs a one-shot instruction to read the named experiment's failing rows and report the dominant failure pattern + current execution_match score, returns the agent's text (or `""` on any error for deterministic fallback).
- Verified the ADK API against google-adk 2.2.0 docs (adk.dev) + source: `McpToolset`/`StdioConnectionParams` from `google.adk.tools.mcp_tool`, `StdioServerParameters` from `mcp`, keyword-only `Runner.run_async`. Phoenix MCP launch args confirmed from Arize-ai/gemini-hackathon `.gemini/settings.json`. Documented Gemini-CLI fallback inline.

## 2026-06-08 — [Team B] integration lane pinned + validated
- Parallel-agent pass built phoenix_client.py, mcp_introspect.py, models.py (above).
- Pinned doc-verified deps in pyproject.toml: google-adk>=2.2.0, google-genai>=2.0.0, arize-phoenix-client>=2.7.0, arize-phoenix-otel>=0.13.0, openinference-instrumentation-google-adk>=0.1.15, mcp>=1.0.0.
- `uv sync` resolves+installs cleanly; all three modules import against the real SDKs; mutation suite still 6/6 green. Committed uv.lock for reproducible team installs. Runtime verification of phoenix/mcp/genai still pending the credentialed spike.
