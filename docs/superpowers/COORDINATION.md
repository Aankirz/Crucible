# Crucible — Team Coordination (Rules of Engagement)

Two sub-teams build Crucible in parallel. This doc is the shared contract: **who owns what, when to merge, and where to stop and sync.** Per-team execution scripts live in `SESSION-TEAM-A.md` and `SESSION-TEAM-B.md`. Implementation code/tasks live in `plans/2026-06-07-crucible.md`.

## Core principle

**Disjoint file ownership + one locked contract = no interruption.** After GATE 0, the two teams touch *different files* through all of Phases 1–5, so merges to `main` are conflict-free. The only shared file is `src/crucible/types.py` — locked at GATE 0.

## The one shared file

`src/crucible/types.py` (and the event shapes in `src/crucible/server/events.py`) are **frozen at GATE 0**. Any change after GATE 0 is a **joint 5-minute decision**, never a silent edit. If you think you need a contract change: post it, both teams ack, one team edits, both rebase.

## Git / merge protocol

- `main` is protected — **never commit directly to `main`.** Everything lands via PR.
- Each team works on its own branches and **merges completed modules to `main` as it finishes them** (small PRs). Because file ownership is disjoint, the other team's daily rebase on `main` is conflict-free.
- Rebase on `main` at least once a day.
- A 🟢 **MERGE GATE** below means: that work must be on `main` before dependent work starts.

## Ownership map (no overlap after GATE 0)

| Team A — Eval Substrate (credential-free) | Team B — Brain + Integration |
|---|---|
| `comparator.py` | `mutation.py` |
| `sandbox.py` | `phoenix_client.py` |
| `datasets/hardness.py` | `mcp_introspect.py` |
| `datasets/spider_loader.py` | `models.py` (gemini adapter) |
| `datasets/split.py` | `scripts/spike_adk_phoenix_mcp.py` |
| `candidate.py` | `orchestrator.py` (built at GATE 1) |
| `eval_engine.py` | `server/app.py` (built at GATE 3) |
| `ui/**` (from GATE 1) | `scripts/run_loop_cli.py`, `scripts/run_prebaked.py`, `Dockerfile` |
| `data/**` (Spider download + curated pool) | |

## The gates (sync + merge points)

Legend: 🟢 merge to `main` · ⛔ blocking dependency · 🤝 cross-team handoff

### 🟢 GATE 0 — Foundation (DONE)
Scaffold + `types.py` + `server/events.py` contract merged to `main`. **Both teams start from here.**

### 🪟 Parallel window (Phases 1–5) — NO interruption
Team A runs `comparator → … → eval_engine`. Team B runs `spike, mutation, phoenix, mcp, models`. Fully disjoint files. Merge your modules as you finish.

### 🔴 GATE 1 — Convergence (orchestrator)
- ⛔ **Team B cannot start `orchestrator.py` until BOTH are on `main`:** Team A's `eval_engine` (3.2) **and** Team B's `mutation` (5.x).
- **Owner: Team B** builds the orchestrator.
- **Team A, in parallel, starts the React UI (`ui/`)** against the frozen event contract — needs nothing from B.
- 🟢 Merge orchestrator → `main`.

### 🔴 GATE 2 — End-to-end
- ⛔ Needs: orchestrator (B) + `models.py`/phoenix/mcp (B) + **🤝 Team A's Spider data drop** (`data/`).
- **Owner: Team B** builds `run_loop_cli.py` and runs the first real loop (needs credentials).
- 🤝 **A → B handoff:** Spider DBs + curated eval pool must be delivered before B's e2e run.
- 🟢 Merge e2e driver → `main`.

### 🔴 GATE 3 — Mission Control
- Team B: `server/app.py` (SSE). Team A: React UI.
- 🤝 They meet at the **SSE event contract** (frozen GATE 0 → integrates without surprises).
- 🟢 Merge server + UI → `main`; verify the live stream together.

### 🔴 GATE 4 — Demo assembly (joint)
- Team B: pre-baked 2-DB results + Cloud Run. Team A: README + demo script + visual polish.
- **Both:** live-demo dry-runs.
- 🟢 Final merge → `main`, tag the submission.

## Suggested cadence (extended hackathon)

| Day | Team A | Team B | Gate |
|---|---|---|---|
| 1 AM | foundation (lead) | review type contract | 🟢 GATE 0 |
| 1–2 | comparator → split | spike + mutation + phoenix/mcp | — |
| 2–3 | candidate → eval_engine + Spider data | finish 4.x + models.py | — |
| 3 | pivot to UI | **orchestrator** | 🟢 GATE 1 |
| 4 | React UI | e2e + server | 🟢 GATE 2 / 3 |
| 5 | README + polish | prebaked + Cloud Run | 🟢 GATE 4 |
| 6 | joint demo dry-runs + buffer | | tag |
