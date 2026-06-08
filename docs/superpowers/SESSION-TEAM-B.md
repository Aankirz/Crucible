# Session Plan — Team B (Brain + Integration)

**Your mission:** build the agent's brain (mutation engine + reflexive loop) and the integration layer (Phoenix tracing, agent-initiated MCP introspection, Gemini adapter, server, deploy). You can **write and unit-test everything credential-free**; only *real-run verification* of the spike/Phoenix/MCP/e2e needs keys.

**Read first:** `COORDINATION.md` (gates + merge protocol) and `plans/2026-06-07-crucible.md` (the actual code for each task).

**Branch:** work on `feat/b-*` branches off `main`; small PR per module, merge to `main` as you finish. Rebase daily.

---

## ✅ Pre-req — GATE 0 is merged + review the contract

The foundation is on `main`. **Your first action: review `crucible/types.py` and `crucible/server/events.py`.** You consume these shapes everywhere — if anything is wrong, now is the only cheap time to change it.

> 🛑 **STOP 0 — ack the contract.** Confirm to Team A that the type + event contracts are good *before* both teams go heads-down. After this, the contract is frozen; changes become a joint decision.

---

## Your lane (credential-free to write; verify with keys when available)

1. **`scripts/spike_adk_phoenix_mcp.py`** — wiring spike (plan Task 0.2). **Run this as soon as you have Phoenix + Google keys.** It de-risks the ADK ↔ Phoenix MCP path everything else assumes. Record findings in the file header.
   - ⚠️ If the ADK `MCPToolset` path doesn't work, switch to the Gemini-CLI fallback transport — but keep the `introspect(name) -> str` interface identical so nothing downstream changes.
2. **`mutation.py`** — failure classify + cluster pick (Task 5.1), then propose + immutable apply (Task 5.2). Import `ModelFn`, `Hypothesis` from `crucible.types`. Fully TDD with fake models.
3. **`phoenix_client.py`** — tracing register + experiment logging + prompt registry (Task 4.1). Thin SDK plumbing; verify against installed `arize-phoenix-client`.
4. **`mcp_introspect.py`** — agent-initiated MCP introspection (Task 4.2). Mirror the working spike exactly. Expose only `introspect_failures(experiment_name) -> str`.
5. **`models.py`** (NEW file) — the `gemini_model()` adapter (plan Task 6.2a). *Put it here, NOT in Team A's `candidate.py`.* Temp 0 for deterministic scoring.

🟢 **MERGE `mutation.py` to `main` as soon as it's green — it's a blocker for the orchestrator.**

---

## 🛑 STOP 1 — GATE 1 convergence (before the orchestrator)

**Do NOT start `orchestrator.py` until BOTH are on `main`:**
- ⛔ your `mutation.py` (5.x), **and**
- ⛔ Team A's `eval_engine.py` (3.2).

🤝 Confirm with Team A that `eval_engine` is merged. **Then** build **`orchestrator.py`** (plan Task 6.1) — the reflexive loop wiring eval + mutation + accept/revert/stop/best-so-far + event emission. It must emit exactly the events in `server/events.py`.

🟢 Merge orchestrator → `main`.

---

## 🛑 STOP 2 — GATE 2 end-to-end (you need A's data)

Before running the real loop (`scripts/run_loop_cli.py`, plan Task 6.2):
- ⛔ orchestrator merged (yours) ✓
- 🤝 **Team A's Spider data drop must be delivered** (`data/world_1.sqlite` + `dev.json` + curated pool). **Wait for this handoff — do not fake it.**
- ⛔ Credentials present in `.env`.

Run the loop end-to-end; confirm the test score climbs and that **`mcp_summary` is non-empty** (proves agent-initiated MCP is live). 🟢 Merge driver → `main`.

---

## 🛑 STOP 3 — GATE 3 Mission Control

Build **`server/app.py`** (SSE + run/approve endpoints, plan Task 7.1) over the orchestrator, publishing to the `EventBus` from `server/events.py`.

🤝 **Integrate with Team A's UI at the SSE contract.** Coordinate the merge — verify the live stream together. Don't merge the server-UI integration solo.

---

## Final (GATE 4 — joint)

- `scripts/run_prebaked.py` — 2 extra DBs for the generality table (Task 8.1).
- `Dockerfile` + Cloud Run deploy (Task 8.2). Verify `npx`/MCP works in-container; if not, keep Cloud Run for API/UI and demo the loop locally — note it in the README.
- 🛑 **Joint demo dry-runs with Team A.** Final merge + tag is shared — coordinate.
