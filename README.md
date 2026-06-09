# 🔥 Crucible

**An agent that builds and self-optimizes text-to-SQL agents — improving from its own [Arize Phoenix](https://phoenix.arize.com/) traces via the Phoenix MCP server.**

Google Cloud Rapid Agent Hackathon — **Arize track**. Built with **Gemini 3** + **Google ADK** + **Arize Phoenix** (MCP).

> Point Crucible at a database. It drafts a text-to-SQL agent, scores it objectively against held-out gold SQL by **execution match**, reads its *own* failing runs through the **Phoenix MCP server**, forms one targeted hypothesis, mutates, and re-scores — climbing a leaderboard until it clears a quality bar. **One database in → one tuned, measured agent out.**

---

## Why this is more than a chatbot

It doesn't answer questions — it **runs a closed self-improvement loop and takes action**: generate → execute SQL in a sandbox → score → **introspect its own traces via MCP** → mutate → promote the winner. The agent uses its **own observability data** to get measurably better, with a human in the loop for approval and promotion.

## How the loop works

```
 ┌──────────────────────────────────────────────────────────────────────┐
 │  spec (prompt + few-shots) ─▶ Candidate Runtime ─▶ SQL Sandbox        │
 │        ▲                          (Gemini 3)        (read-only exec)   │
 │        │                                                │              │
 │   Mutation Engine                                 Execution-Match      │
 │   (one atomic fix)                                  Comparator         │
 │        ▲                                                │              │
 │        │                                                ▼              │
 │   Phoenix MCP  ◀── reads its OWN failing traces ── Phoenix Experiment  │
 │   introspection        + leaderboard                  (leaderboard)    │
 └──────────────────────────────────────────────────────────────────────┘
   accept on TRAIN ↑  ·  report on held-out TEST  ·  keep best-so-far  ·  promote on approval
```

Key honesty safeguards (the things a judge will probe):
- **Execution match**, not string match → credits correct-but-differently-written SQL.
- **Held-out test split** → the reported climb proves generalization, not memorization.
- **Human-authored gold** (Spider/BIRD) → the agent never grades against answers it invented.
- **Temperature 0** → every leaderboard number is reproducible.
- **Mutations accepted only on train improvement**, best-so-far always retained, early-stop on no progress.

## Architecture

| Unit | File | Responsibility |
|---|---|---|
| Types (contract) | `src/crucible/types.py` | Shared dataclasses + the `ModelFn` LLM seam |
| Comparator | `src/crucible/comparator.py` | Execution-match over result sets (pure) |
| Sandbox | `src/crucible/sandbox.py` | Read-only, timeout-bounded SQLite execution |
| Datasets | `src/crucible/datasets/` | Difficulty classifier, Spider loader, stratified split |
| Candidate | `src/crucible/candidate.py` | Render prompt from spec, extract SQL |
| Eval engine | `src/crucible/eval_engine.py` | Score a candidate over a split |
| Mutation | `src/crucible/mutation.py` | Classify failures, pick cluster, propose+apply one atomic fix |
| Models | `src/crucible/models.py` | Gemini adapter (`ModelFn`), 429/503 retry, temp 0 |
| Phoenix | `src/crucible/phoenix_client.py` | OTel tracing, experiment logging, prompt registry |
| MCP introspect | `src/crucible/mcp_introspect.py` | Agent-initiated Phoenix MCP read of its own traces |
| Orchestrator | `src/crucible/orchestrator.py` | The reflexive loop |
| Server | `src/crucible/server/` | FastAPI SSE event stream + run/approve |
| Mission Control | `ui/` | React dashboard: live leaderboard, hypothesis, approval |

## Quickstart

```bash
uv sync              # install (Python 3.11/3.12)
uv run pytest -q     # 35/35 green — the whole loop, proven on deterministic fakes
```

### See the loop climb — no API key required
```bash
uv run python scripts/offline_demo.py
```
Runs the **real** orchestrator loop on a **real** SQLite database with real SQL execution (deterministic scripted model standing in for the LLM). Held-out test score climbs **50% → 100%** over 3 accepted mutations.

### Run it with live Gemini 3
```bash
cp .env.example .env          # add GOOGLE_API_KEY (aistudio.google.com/apikey)
uv run python scripts/live_gemini_demo.py
```
> ⚠️ Gemini's free tier caps a project at ~20 requests/day; a full climbing run is ~30–40 calls. Use billing or a budgeted tiny set for a complete live run. `gemini-3-pro` needs billing (free limit 0); `gemini-3-flash-preview` works on the free tier.

### Full live e2e (Gemini + Phoenix + MCP)
```bash
# .env also needs: PHOENIX_API_KEY, PHOENIX_COLLECTOR_ENDPOINT, plus Spider data (see data/README.md)
make spike                              # confirm ADK ↔ Phoenix ↔ MCP wiring
uv run python scripts/run_loop_cli.py  # real climb on Spider world_1, traced to Phoenix
```

### Mission Control UI
```bash
make serve                       # FastAPI SSE backend on :8000
cd ui && npm install && npm run dev   # dashboard; append ?demo=1 to replay a climb with no backend
```

## Demo script (90 seconds)

1. **`uv run pytest -q`** → 35/35. "The whole self-improvement loop is proven."
2. **`uv run python scripts/offline_demo.py`** → watch test score climb 50%→100% on real SQL, credential-free.
3. **UI** (`?demo=1`) → the same climb as a live mission-control leaderboard with the agent's hypotheses.
4. **Live** (with billing/Phoenix) → `run_loop_cli.py`: Gemini 3 generates SQL, the agent reads its **own** Phoenix traces via **MCP** to drive each fix, leaderboard climbs on the real Phoenix dashboard. **Promote on approval.**

## Project docs

- Design spec: `docs/superpowers/specs/2026-06-07-crucible-design.md`
- Implementation plan: `docs/superpowers/plans/2026-06-07-crucible.md`
- PRD: `docs/superpowers/prds/2026-06-07-crucible.md` (also GitHub issue #2)

## Status

Core loop, eval substrate, mutation engine, Phoenix/MCP integration modules, server, and UI are built; **35/35 tests green**; offline real-SQL climb proven. Remaining: live multi-version climb on Gemini 3 (needs billing or budgeted quota) and the Phoenix-traced e2e (needs Phoenix key + Spider data).
