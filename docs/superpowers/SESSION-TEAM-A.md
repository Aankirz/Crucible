# Session Plan — Team A (Eval Substrate)

**Your mission:** build the credential-free evaluation substrate — the pure-Python core that runs candidate agents, executes SQL safely, and scores them objectively. You need **no API keys** for your entire lane.

**Read first:** `COORDINATION.md` (gates + merge protocol) and `plans/2026-06-07-crucible.md` (the actual code for each task — follow its TDD steps exactly).

**Branch:** work on `feat/a-*` branches off `main`; open a small PR per module and merge to `main` as you finish. Rebase on `main` daily.

---

## ✅ Pre-req — GATE 0 is merged
The foundation (`types.py`, `server/events.py`, scaffold) is on `main`. Import all shapes from `crucible.types`. **Do not redefine types locally.**

> 🛑 **If you believe you need a change to `types.py`:** STOP. Post it to Team B, get an ack, one team edits, both rebase. Never edit the contract silently.

---

## Your lane (do in order — all credential-free, all TDD)

Each item = a task in `plans/2026-06-07-crucible.md`. Write the failing test, watch it fail, implement, watch it pass, commit. Merge each to `main` when green.

1. **`comparator.py`** — execution-match (plan Task 1.2). *Crown jewel — get this rock-solid first.*
2. **`sandbox.py`** — read-only SQLite + timeout (Task 1.3).
3. **`datasets/hardness.py`** — difficulty classifier (Task 2.1).
4. **`datasets/spider_loader.py`** — load gold → `EvalItem[]` (Task 2.2).
5. **`datasets/split.py`** — stratified split + weighted sample (Task 2.3).
6. **`candidate.py`** — prompt render + SQL extract + `run_candidate_on_item` (Task 3.1). *Import `ModelFn` from `crucible.types`, do NOT define it here.*
7. **`eval_engine.py`** — score a candidate over a split (Task 3.2). *This integrates your comparator + sandbox + candidate.*

🟢 **MERGE `eval_engine` to `main` as soon as it's green — Team B is blocked on it for the orchestrator.** Tell Team B the moment it lands.

8. **🔧 Data drop (start in parallel, finish by GATE 2):** download Spider, place `world_1.sqlite` + `dev.json` under `data/`, and build the curated, difficulty-weighted eval pool. Commit a small `data/README.md` describing exact paths.

---

## 🛑 STOP 1 — after `eval_engine` is merged

**Do NOT build `orchestrator.py`. That is Team B's file.** Your eval substrate is done.

- Confirm `eval_engine` is on `main`.
- 🤝 Confirm with Team B that they have what they need to start the orchestrator (GATE 1).
- **Then pivot to your next assignment below — do not idle.**

---

## Next assignment (during GATE 1) — React Mission Control UI

While Team B builds the orchestrator, build the UI (plan Task 7.2) in `ui/`.

- Build **entirely against the frozen SSE event contract** in `crucible/server/events.py` (`VersionEvent`, `HypothesisEvent`, `RejectedEvent`, `PromotedEvent`). You need **nothing** from Team B's server yet — mock the event stream locally.
- Deliver: leaderboard (climbing test %), live hypothesis card, approval/promote controls.

> 🛑 **STOP 2 — GATE 3 integration.** Do NOT wire the UI to the live backend until Team B's `server/app.py` is merged to `main`. When it is, integrate against the real SSE endpoint and **verify the live stream together with Team B.** If the event shapes feel wrong, that's a joint contract change — raise it, don't patch around it.

---

## 🤝 Hard handoff you owe Team B

**The Spider data drop must be delivered before GATE 2** (Team B's first end-to-end run). This is a blocking dependency for them — don't let it slip behind your UI work.

---

## Final (GATE 4 — joint)

- README + demo script + visual polish (plan Task 8.3).
- 🛑 **Joint demo dry-runs with Team B.** Final merge + tag is a shared step — coordinate, don't merge solo.
