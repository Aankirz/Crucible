# Crucible — Design Spec

**Date:** 2026-06-07
**Status:** Design locked (grilling complete). Ready for implementation planning.
**Author:** Ankit
**Hackathon:** Google Cloud "Rapid Agent" Hackathon — **Arize track**.

---

## 1. Product thesis

**Crucible is an agent that builds text-to-SQL agents.** Point it at a database and it autonomously builds, evaluates, and optimizes a text-to-SQL agent specialized for *that* schema — improving by reading **its own** run traces through the Arize Phoenix MCP server, until it clears a quality bar. The promoted artifact is a deployable, tuned agent with a proven score.

**One database in → one tuned agent out.** Specialization is per-DB by design: the highest-ROI levers (few-shot exemplars, join-path instructions) are schema-specific, so the optimization re-runs per database.

## 2. Why this wins the Arize bucket

The Arize track scores: *technical implementation, meaningful use of tracing and MCP, **quality of the agent's self-improvement loop**, and overall impact*, with *bonus for agents that use their own observability data to improve over time.*

Crucible **is** that self-improvement loop end-to-end — not tracing bolted onto a chatbot. Rubric mapping:

| Rubric item | How Crucible satisfies it |
|---|---|
| Technical implementation | Google ADK + Gemini 3 on Cloud Run; Phoenix tracing; FastAPI + React Mission Control. |
| Meaningful tracing + MCP | The agent **reads its own failing traces + experiment leaderboard via Phoenix MCP** to decide each next mutation, and **promotes** the winning prompt via MCP. Decision-critical, not decorative. |
| Self-improvement loop quality | The entire product. Measurable, visible, reverting/early-stopping, generalization-tested. |
| Overall impact | Automated, eval-driven agent optimization is a real pain for every AI team. |

## 3. Scope guardrails (hackathon-pragmatic)

- **Databases are always Spider/BIRD DBs**, which ship **human-authored gold SQL**. This deliberately avoids the arbitrary-DB "no ground truth" problem — gold is always the benchmark's human SQL. No self-authored golds, no bootstrapping.
- Demo proves generality with **3 DBs** (see §10), not by claiming truly arbitrary DBs.

## 4. Architecture (7 focused units)

1. **Orchestrator** (ADK + Gemini 3) — runs the reflexive loop, owns decisions, holds the Phoenix MCP toolset on its introspection sub-agent.
2. **Eval Engine** — loads the benchmark dataset, applies train/test split + difficulty weighting, runs candidates as Phoenix experiments.
3. **Candidate Runtime** — instantiates a text-to-SQL agent from a `(prompt, few-shots, tool/context config)` spec, runs it over the dataset, traced via OpenInference.
4. **SQL Sandbox** — read-only SQLite connection + statement timeout + the **execution-match comparator** (§6).
5. **Phoenix MCP Client** — agent-facing tool layer: read traces/spans, read experiment results, write/promote prompts.
6. **Mutation Engine** — clusters failures, forms one atomic hypothesis, emits the next candidate spec.
7. **Mission Control (UI + API)** — FastAPI SSE stream + React: leaderboard, hypothesis, prompt diff, failure-cluster bars, approval/promote gates.

## 5. The reflexive loop

```
load DB + benchmark gold → train/test split (difficulty-weighted)
  → draft candidate v1 (schema pre-loaded, baseline instruction, no few-shots)
  → Candidate Runtime runs over TRAIN set (traces → Phoenix)
  → Eval Engine scores execution-match → logs Phoenix experiment
  → Orchestrator (agent-initiated MCP): read failing spans + leaderboard
  → Mutation Engine: cluster failures → pick highest-impact cluster → ONE atomic mutation
  → [human approve / autopilot]
  → candidate v(n+1) → re-run → score
  → accept if TRAIN improves; else revert; track TEST (held-out) as headline number
  → loop until stop criteria (§ stopping)
  → keep BEST-so-far → [human approve] → promote prompt to Phoenix registry (via MCP)
     + export deployable ADK agent
```

**Accept/report split:** mutations are driven and accepted on **dev/train** improvement; the **held-out test** score is the headline leaderboard number per version (proves generalization, not memorization).

## 6. Eval design

- **Ground truth:** benchmark human gold SQL.
- **Split:** ~40 train (agent learns from observed failures here) / ~30 held-out test (scored, never seen during mutation). Per DB.
- **Difficulty mix** (so the stronger v1 keeps headroom): ~20% easy / 35% medium / 30% hard / 15% extra-hard (Spider hardness labels). Target v1 ≈ 55–65% test, climbing to ~90%. Keep a few easy items to demonstrate "no regression on basics."
- **Comparator semantics** (TDD target #1):
  - Order-**insensitive** unless gold contains `ORDER BY` (then order-sensitive).
  - **Multiset** row comparison (duplicates count — catches `COUNT` vs `COUNT(DISTINCT)`).
  - **Strict columns**: same column count + positional values; ignore names/aliases; no permutation-matching.
  - **Type-normalized**: numeric tolerance, `strip()` strings, NULL-aware equality.
  - Predicted SQL that errors or exceeds statement timeout → **score 0**, capture error string (feeds the hypothesis).

## 7. Mutation engine

- **Mutable levers:** system-prompt instructions + few-shot exemplars + which tools/context are enabled. **Model temperature pinned at 0** (determinism → reproducible scores). Temp/params and tool authorship are *not* MVP levers (stretch).
- **v1 baseline:** schema pre-loaded in context + a plain instruction, no few-shots.
- **Failure taxonomy:** schema/column, JOIN, aggregation/GROUP BY, nested/subquery, ORDER BY/LIMIT, value-format, syntax/execution.
- **Per round:** pick the highest-impact (most failures) cluster → propose ONE atomic mutation targeting it (e.g., add 2–3 few-shots of that pattern + one instruction line). Atomic = attributable gains.

## 8. Stopping criteria & guardrails

Stop on **any** of: held-out test ≥ bar (default **90%**) · **6** iterations · token/cost budget exhausted · **2 consecutive non-improving rounds** (early-stop → revert to best). Demo caps ~5 iterations. Always promote **best-so-far**.

## 9. Phoenix + MCP integration (hybrid)

- **Deterministic code/SDK** (must not flake): emit traces, create experiment records, run evals.
- **Agent-initiated via Phoenix MCP** (the rubric beat): each round the agent calls MCP to **read its own failing spans + experiment leaderboard** (drives the hypothesis), and to **promote the winning prompt** to the registry. These appear as tool spans.
- **Reliability:** introspection is a dedicated agent turn with MCP tools scoped to that step + a code fallback if the tool call misfires.
- **Wiring risk:** validate ADK `MCPToolset` ↔ `@arizeai/phoenix-mcp` (npx/stdio) in hour 1; fallback = quickstart's Gemini-CLI MCP pattern. Fork starter: `github.com/Arize-ai/gemini-hackathon`.

## 10. Demo plan

- **1 live** (`world_1`): trigger the loop, watch test score climb ~60% → ~90% with narrated hypotheses; approve first mutation + final promotion; show the real Phoenix dashboard alongside.
- **2 pre-baked**: same untouched loop run offline on 2 other Spider/BIRD DBs (different domains, e.g. a BIRD financial DB), shown as a results table → proves "same loop generalizes across schemas," no live time spent.

## 11. Tech stack

Gemini 3 · Google ADK on Cloud Run · Arize Phoenix Cloud (free tier: datasets/experiments/evals/prompts/traces) · `@arizeai/phoenix-mcp` · OpenInference auto-instrumentation · SQLite (benchmark DBs) · Python 3.11 + uv · FastAPI (SSE) · React/Vite.

## 12. MVP / stretch / cut

- **MVP (must-win):** reflexive loop, execution-match comparator, train/test split, agent-initiated MCP introspection + promotion, Mission Control leaderboard + approval, `world_1` live + 2 pre-baked.
- **Stretch:** tool/param mutation (beyond prompt/few-shots), evolutionary "turbo" mode, one-click Cloud Run deploy of the promoted agent, BIRD-hard showcase.
- **Cut:** auth, multi-tenant, persistence beyond Phoenix, anything off the demo path.

## 13. Build order (tracer bullet first)

1. **Comparator** (TDD) → 2. SQLite sandbox + `world_1` + 5-example set → 3. minimal traced candidate agent → 4. eval → Phoenix experiment → 5. agent reads own failures via MCP → 6. one mutation → v2 → 2-row leaderboard (**loop closed end-to-end**) → 7. breadth: full eval set, split, more iterations, Mission Control UI, 2 pre-baked DBs, Cloud Run, polish.

## 14. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Live loop slow/costly on stage | Pre-warm, cap ~5 iterations, recorded fallback clip. |
| Overfitting critique | Held-out test split is the headline number; say so explicitly. |
| MCP/ADK toolset flakiness | Hour-1 spike; Gemini-CLI fallback; code fallback for introspection. |
| Score jitter | Temp 0 everywhere; deterministic comparator. |
| "Writes its own tools" overreach | MVP bounded to prompt + few-shots + tool *enablement*, not arbitrary codegen. |

## 15. Open questions (non-blocking)

- Final product name (Crucible = working title).
- Exact 2 pre-baked DBs (1 BIRD financial + 1 Spider TBD).
- Whether the Cloud Run "deploy promoted agent" finale is fully wired or partially staged for the demo.
