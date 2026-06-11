# Crucible — Devpost Submission

> Google Cloud "Rapid Agent" Hackathon — Arize Track
> Copy-paste ready. Each section maps to a Devpost form field.

---

## 1. Elevator pitch (short tagline — ≤200 chars)

One database in → one tuned, measured text-to-SQL agent out. Crucible reads its own Arize Phoenix traces via MCP, hypothesizes the dominant failure, mutates, and re-scores until it wins.

---

## 2. Inspiration

Everyone can prompt an LLM to write SQL. Almost nobody can prove it got better. We wanted an agent that doesn't just generate text-to-SQL — it *measures itself against human gold answers, reads its own failures, and fixes the right thing next*. Not "looks plausible." Real SQL, executed against a real database, scored against gold. The crucible is the test: only mutations that survive measurement get to stay.

---

## 3. What it does

Crucible builds and **self-optimizes** text-to-SQL agents. Give it a database (Spider/BIRD-style) and it runs a closed reflexive loop:

1. **Draft** a candidate text-to-SQL agent.
2. **Score** it by execution-match against human gold SQL on a held-out test split — real SQL run against a real SQLite database, no estimates or mocks.
3. **Introspect** its OWN failing traces by reading them back through the Arize Phoenix MCP server.
4. **Hypothesize** — form one atomic hypothesis about the dominant failure cluster.
5. **Mutate** the agent to address exactly that cluster.
6. **Re-score** and climb a leaderboard until it clears the quality bar.

**ML hygiene is enforced, not decorative:** accept a mutation only if it improves the **TRAIN** split, report on a **HELD-OUT** test set that is never optimized against, keep best-so-far, and patience early-stop.

---

## 4. How we built it

**Reasoning:** Gemini 3 drafts agents, reads failing traces, forms hypotheses, and writes mutations.

**Observability + self-introspection:** Arize Phoenix for tracing, scored experiments, and — the core trick — **MCP self-introspection**: a Gemini agent reads its own failing Phoenix experiment back through the Phoenix MCP server to drive the next fix. The agent's eval substrate *is* its feedback channel.

**App:** FastAPI + React "Mission Control" UI streaming the climb live over SSE. Python, uv, 65 passing tests.

**Five architecture layers:**

1. **Eval substrate** — read-only SQLite sandbox + an execution-match comparator (multiset rows, order-sensitive only on top-level `ORDER BY`, numeric-tolerant, NULL-aware).
2. **Reflexive optimization loop** — draft → score → introspect → hypothesize → mutate → re-score.
3. **Mutation engine** — turns one atomic hypothesis into one targeted change.
4. **Phoenix tracing / experiments / MCP introspection** — the agent reads its own failures.
5. **Mission Control UI** — live SSE stream of the leaderboard climb.

---

## 5. Challenges we ran into

- **A *fair* execution-match comparator.** Naive row-equality is wrong: result sets are multisets, ordering only matters when the query has a top-level `ORDER BY`, floats need tolerance, and NULLs need explicit handling. Getting this right was the difference between a real score and a lie.
- **Wiring agent-initiated MCP introspection.** Making a Gemini agent reach back through the Phoenix MCP server to read its *own* failing experiment — and feed that into the next mutation — was the hardest plumbing in the project.
- **LLM rate limits.** Keeping the climb reproducible and the demo deterministic while respecting live-model throughput meant careful batching and an offline replay path.

---

## 6. Accomplishments we're proud of

- **A genuine, measured 50% → 100% climb** on a held-out test set over 3 accepted mutations — every score is real SQL executed against a real SQLite database and compared to gold.
- **Failure clusters fixed in the right order:** JOIN → aggregation → ordering. The agent didn't flail; it attacked the dominant cluster each round.
- **An agent that reads its own Phoenix traces via MCP** to decide what to fix next — true self-introspection, not a scripted heuristic.
- **A fully reproducible, tested system:** 65 passing tests, deterministic offline demo, real eval substrate.

---

## 7. What we learned

Measurement, not generation, is the hard part — a fair, executable comparator plus train/test discipline turns "the LLM wrote some SQL" into "the agent provably got better." Giving an agent read access to its own traces (via MCP) makes self-improvement concrete instead of hand-wavy.

---

## 8. What's next

- **Multi-DB / BIRD generalization** — climb across many databases, not one.
- **Funded live Gemini** for on-demand climbs straight from the UI.
- **Promote winning prompts to the Phoenix prompt registry** so proven agents become reusable artifacts.

---

## 9. Built with

gemini, google-adk, arize-phoenix, mcp, fastapi, react, vite, python, sqlite, sse, uv, render

---

## 10. Try it

- **Hosted:** https://crucible-api-md84.onrender.com
- **Repo:** https://github.com/Aankirz/Crucible
- **Run the offline demo (deterministic, no API keys):**

```bash
uv run python scripts/offline_demo.py
```
