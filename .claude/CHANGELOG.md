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

## 2026-06-09 — Eval substrate (single-team build)
- Dropped the two-team split; building solo now.
- Added (TDD): comparator.py, sandbox.py, datasets/{hardness,spider_loader,split}.py, candidate.py, eval_engine.py.
- Full suite 33/33 green.

## 2026-06-09 — Orchestrator loop (tracer bullet closed)
- Added src/crucible/orchestrator.py: reflexive loop (score → introspect → cluster → atomic mutation → accept-on-train / report-on-held-out-test → best-so-far → promote) with target/max-iters/patience stopping.
- Full suite 35/35 green; loop proven (improves to target; early-stops on no improvement) on fakes — no credentials needed.

## 2026-06-09 — Mission Control FastAPI backend + Cloud Run image
- Created src/crucible/server/app.py: SSE event stream (GET /events), POST /run (background loop thread), POST /approve (threading.Event approval gate), startup init_tracing wrapped in try/except, permissive CORS, local read-only read_schema helper. Wires the orchestrator loop to the EventBus.
- Created Dockerfile (python:3.11-slim + nodejs/npm for npx Phoenix MCP, uv sync, uvicorn on 8080) and .dockerignore for Cloud Run deploy.

## 2026-06-09 — Runtime driver scripts (spike, live loop, prebaked) + data README
- Created scripts/spike_adk_phoenix_mcp.py: ADK<->Phoenix<->MCP wiring spike. Mirrors crucible.mcp_introspect construction exactly (LlmAgent, McpToolset + StdioConnectionParams, `from mcp import StdioServerParameters`, Runner + InMemorySessionService, run_async), reuses init_tracing(), runs one Phoenix-MCP agent turn, prints output + "SPIKE OK". Manual confirmation only (no test).
- Created scripts/run_loop_cli.py: end-to-end loop on world_1. read_schema(db_path) read-only helper, weighted_sample(70)/stratified_split(0.43), gemini_model() as candidate+mutation model, introspect_failures + log_experiment wired, on_event=print, LoopConfig(max_iters=5, target=0.9, patience=2). Prints BEST + HISTORY.
- Created scripts/run_prebaked.py: offline loop over 2 extra DBs (concert_singer + BIRD financial), reuses run_loop_cli.read_schema, writes data/prebaked_results.json as {db_id: {final_test, history}}.
- Created data/README.md: Spider/BIRD download + placement instructions matching CRUCIBLE_DB_PATH/CRUCIBLE_SPIDER_DEV env vars; notes BIRD financial DB normalization for prebaked.
- Imported gemini_model from crucible.models (not candidate, per scope). All three scripts py_compile clean. No modules modified.

## 2026-06-09 — Add offline credential-free demo
- Created scripts/offline_demo.py: runs the real orchestrator.run_loop against a real SQLite "world" DB with real SQL execution, using deterministic scripted candidate/mutation models (no API/credentials). Test score climbs 50% -> 100% over 3 accepted mutations. No existing modules modified; 35/35 tests still pass.

## 2026-06-09 — Demo surface (parallel-agent pass): server, UI, scripts, offline demo
- FastAPI Mission Control backend (src/crucible/server/app.py): SSE /events, /run (bg thread), /approve gate; try/except Phoenix tracing; Dockerfile + .dockerignore for Cloud Run.
- React "mission control" UI (ui/): leaderboard with hero held-out Test %, hypothesis card, controls, promoted banner; built-in mock climb (?demo=1) so it runs with no backend. npm run build passes.
- Runtime scripts: spike_adk_phoenix_mcp.py (live wiring), run_loop_cli.py (real e2e), run_prebaked.py (2-DB generality), data/README.md.
- offline_demo.py: runs the REAL orchestrator loop on a real temp SQLite DB with a scripted model — climbs 50%→100% (3 accepted mutations) credential-free.
- Packaging: added [build-system] (hatchling) so `crucible` installs as a package; bare `uv run`/uvicorn imports now work without PYTHONPATH. Full suite 35/35 green.

## 2026-06-09 — Live Gemini wired + hardened (free-tier quota hit)
- Captured GOOGLE_API_KEY into .env (gitignored). Confirmed models.py works against LIVE Gemini 3 (real SQL generated).
- Fixed invalid default model id (gemini-3-pro -> gemini-3-flash-preview; pro needs billing, free limit 0).
- Hardened gemini adapter: retry/backoff on 429 (parse retryDelay / 'retry in Xs') and 503 (overloaded).
- Added scripts/live_gemini_demo.py: real loop on a real bundled SQLite "world" DB driven by live Gemini (Phoenix stubbed).
- BLOCKER: Gemini free tier caps the project at ~20 requests/day; a full climbing run needs ~30-40 calls -> needs billing or a budgeted tiny run. Offline demo remains the mechanical climb proof (50%->100%).

## 2026-06-09 — README + demo script (Phase 8.3)
- Rewrote README.md: pitch, loop diagram, honesty safeguards, architecture table, quickstart (offline demo / live Gemini / full e2e / UI), 90-second demo script, status. Completes the last credential-free master-plan item.
