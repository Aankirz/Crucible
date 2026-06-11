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

## 2026-06-09 — Review hardening (3 parallel agents: tests + code review + security)
- Added 28 tests (test_models, test_phoenix_client, test_server) → suite now 63 passing.
- CRITICAL fix: MCP introspection never fired (orchestrator looked up an experiment name that didn't match what phoenix_client logged, and train split was never logged). Now logs the train split and uses the name log_experiment returns → introspection reads real failures.
- HIGH: eval_engine now surfaces broken-gold-SQL errors and excludes them from the score (was silently scored as agent failure, skewing the leaderboard); EventBus made thread-safe via bind_loop + call_soon_threadsafe (cross-thread publish could freeze SSE); propose_mutation tolerates non-JSON model replies (was crashing the loop).
- MEDIUM: weighted_sample tops up to n (rounding left it short); gold_requires_order is depth-aware (subquery ORDER BY no longer forces ordered match); empty mutation no longer wastes a version.
- SECURITY: Phoenix API key no longer passed as npx CLI arg (argv leaks via ps) — env only, in mcp_introspect.py + spike. No secrets committed (verified).
- Offline demo still climbs 50%→100%.

## 2026-06-09 — Vertex AI mode (use Cloud credits)
- models.py: gemini_model() now supports two auth modes via `_build_client`: Vertex AI (GOOGLE_GENAI_USE_VERTEXAI=true + project/location + ADC) to consume Google Cloud credits with no daily cap, or AI-Studio API key (default). +2 tests (65 total). Documented both modes in .env.example.

## 2026-06-12 — Live Phoenix Cloud + MCP introspection wired
- Wired real Phoenix Cloud creds into .env (gitignored): PHOENIX_API_KEY + space endpoint https://app.phoenix.arize.com/s/sahuankit453.
- Verified tracing end-to-end: init_tracing() emits spans that land in the Phoenix `crucible` project (confirmed via spans query).
- Ran the ADK+Phoenix MCP spike: Gemini agent connected to @arizeai/phoenix-mcp and listed the live Phoenix space (projects: crucible, demo_llama_index, default) — SPIKE OK.
- Added scripts/phoenix_e2e.py: logs a REAL failing experiment (crucible-world-v1-train) to Phoenix via phoenix_client.log_experiment, then runs live MCP introspection. Experiment logging confirmed in Phoenix Cloud.
- Live MCP introspection step currently blocked by transient Gemini 503 "high demand" (capacity, not quota/wiring); patient background retry in place.

## 2026-06-12 — Bake real optimization climb into UI replay data
- Added scripts/bake_replay.py: runs the real crucible.orchestrator.run_loop offline (deterministic, no-API) and captures emitted loop events in order with natural pacing delays.
- Generated ui/src/replayData.ts (REAL_CLIMB) from the real run: genuine 50%->100% held-out test climb across versions 1-4 with truthful Phoenix-MCP-style hypothesis summaries.

## 2026-06-12 — Real live deploy: bundled-world backend + Render/Vercel wiring
- Removed UI mock/replay path entirely (no fake data): deleted ui/src/replayData.ts + scripts/bake_replay.py; useEvents.ts now reflects only the live backend (connecting/live/error), API base via VITE_API_URL.
- Added src/crucible/datasets/world_bundle.py: self-contained real "world" SQLite + human-authored gold SQL (verified every gold query executes). Server falls back to it when no Spider data is configured, so it runs the REAL loop on real data with zero external download.
- server/app.py: bundled-world mode (build DB at startup, world train/test splits, no-schema v1 for an honest climb), added /healthz.
- Dockerfile: Python 3.12 + Node, pre-installs @arizeai/phoenix-mcp, binds $PORT (Render).
- render.yaml blueprint + DEPLOY.md runbook (Vertex/AI-Studio + Render + Vercel). 65 tests green.

## 2026-06-12 — Single-service deploy (FastAPI serves UI) + free-tier hardening
- FastAPI now serves the built Vite UI at "/" when CRUCIBLE_UI_DIST is set (same-origin, no Vercel/CORS). Smoke-tested: /healthz, /, /assets all 200.
- Dockerfile is now multi-stage: stage 1 builds the UI (VITE_API_URL="" -> same-origin), stage 2 runs FastAPI serving both. One Render service = whole app.
- models.py: multi-key rotation via GOOGLE_API_KEYS (pool free-tier 20/day across projects; rotate on 429/503).
- render.yaml: GEMINI_MODEL -> gemini-3-flash-preview (free-tier safe), GOOGLE_API_KEYS option. 65 tests green.

## 2026-06-12 — Pitch deck visual polish
- slides/index.html: added hover/active states (card, step, layer, vbox, figure, pill), dot focus-visible a11y outline, reduced-motion support, and fixed orphaned 5th loop step on mobile. CSS-only, inline, offline-safe. No behavior or numbers changed.

## 2026-06-12 — Hosted UI demo mode (real climb, no funded LLM)
- Added CRUCIBLE_DEMO mode: /run streams the REAL run_loop on the bundled world DB with the offline scripted models (real SQL execution, real 50->100% scores), paced ~1.1s/event so the leaderboard animates live. Verified events stream end-to-end. UI feed pill flips to live on SSE open.
- render.yaml: CRUCIBLE_DEMO=1 so the hosted app always shows a working climb. 65 tests green.
## 2026-06-12 — Fact-check pitch deck climb numbers
- slides/index.html Slide 4: corrected the climb visualization to show all four spec versions (v1 50%, v2 75%, v3 75%, v4 100%) with fix tags in the actual order (JOIN -> aggregation -> ordering), matching the real offline_demo.py run. Previously the deck collapsed the climb into v1/v2/v4 and mislabeled the per-version fix tags.

## 2026-06-12 — Harden live MCP introspection (retry transient 503s)
- mcp_introspect.introspect_failures now retries transient failures (503/overload/429) up to 3x with backoff before falling back to the deterministic classifier; fails fast on terminal errors (missing creds). Added _is_transient helper. +5 tests (test_mcp_introspect.py). 70 tests green.

## 2026-06-12 — Demo run logs REAL Phoenix experiments (async)
- _async_log_experiment: demo mode now logs genuine EvalResults to Phoenix in a background thread, so clicking Run on the hosted app populates the Arize Phoenix space with real experiments while the UI climb stays snappy (non-blocking, best-effort). 70 tests green.

## 2026-06-12 — VERIFIED LIVE END-TO-END (Vertex AI + Phoenix + MCP)
- Switched to Vertex AI (gemini-3-flash-preview, location=global) drawing the Google Cloud $300 trial credits — the AI-Studio prepay key could not use them. ADC re-authed as aankir101 (project gen-lang-client-0589427141, billing linked, Vertex API enabled).
- Verified live: real Gemini 3 climb; and the full Arize money shot — real flow -> real Phoenix experiment -> Gemini agent reads its OWN failures via the Phoenix MCP server and correctly diagnoses JOIN/GROUP BY/ORDER BY omissions (execution_match=0.4 matched). PROOF.md added.

## 2026-06-12 — Multi-DB catalog + richer SSE events (v2 contract)
- Added 3 self-contained Spider-style benchmark DBs (concert_singer, university, ecommerce), each with CREATE TABLE schema, INSERT rows, and 13 hand-authored EvalItems (8 train / 5 test) covering JOIN, GROUP BY/HAVING, ORDER BY+LIMIT, and subquery patterns. All 39 gold SQL verified to execute against their bundled SQLite DBs.
- Added crucible/datasets/catalog.py registry: DatabaseDescriptor + build_db/get_items/get_schema; world=mode "demo", the 3 new ones=mode "live".
- app.py: new GET /databases and GET /schema endpoints; /run is now catalog-aware (world->deterministic demo path, live DBs->real Gemini via _run_live_job) and returns mode in its ack. Live runs bounded by CRUCIBLE_MAX_ITERS (default 3).
- Emitted new SSE events (status/item/phoenix/run_complete) in both demo and live paths, matching the frozen UI_API_CONTRACT ordering. Phoenix deep link built from PHOENIX_COLLECTOR_ENDPOINT (else "").
- eval_engine.evaluate + orchestrator.run_loop gained an OPTIONAL on_item callback (default None) so existing callers/signatures stay backward-compatible.
- render.yaml: documented CRUCIBLE_MAX_ITERS.
- tests/conftest.py: neutralize a local .env's Vertex vars so the deterministic suite is not order-dependent (fixes a pre-existing test_models flake when test_server imports app first).
- Added tests/test_catalog.py + new on_item/endpoint tests. Full suite: 100 passed (70 existing + 30 new).

## 2026-06-12 — Landing page + multi-DB picker + step-by-step console (parallel build)
- Frozen UI/API contract (docs/UI_API_CONTRACT.md). Backend + frontend built in parallel against it.
- Backend: 3 new bundled DBs (concert_singer, university, ecommerce; 39 gold SQL all execute) + catalog.py; GET /databases, GET /schema; catalog-aware /run (world=demo instant, live DBs=real Gemini, CRUCIBLE_MAX_ITERS bound). Richer SSE events: status/item/phoenix/run_complete via optional on_item callback threaded through evaluate+run_loop (backward compatible). 100 tests pass.
- Frontend: landing hero + CTAs + loop diagram, How-it-works, live Console (DB dropdown w/ demo|live badge, schema viewer, step-by-step ActivityLog showing each generated SQL ✓/✗, Phoenix panel with experiment links, leaderboard, hypothesis), Bring-your-own-DB guide, footer. Build green.
- Verified integration: /databases (4), /schema, and item/status/phoenix events stream end-to-end.
