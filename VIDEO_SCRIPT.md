# Crucible — 2-minute demo voiceover script

**Track: Arize · Gemini 3 + Arize Phoenix MCP**
Read at a calm pace. ~300 words ≈ 2:00. Each block lists WHAT TO SHOW while you read it.

---

### 0:00–0:15 · Hook
**SHOW:** Hosted app — `https://crucible-api-md84.onrender.com` (Crucible Mission Control).

> "This is Crucible. Most agents answer questions. Crucible *builds and tunes other agents.* You hand it a database, and it ships back a text-to-SQL agent that has measurably taught itself to get better."

---

### 0:15–0:35 · The problem
**SHOW:** Stay on the UI — point at the "Current Hypothesis" and "Leaderboard" panels.

> "Writing a good text-to-SQL agent is guesswork — you tweak a prompt and hope. Crucible turns that into a measured loop: draft an agent, score it against human gold answers, read *why* it failed, fix one thing, and re-score on a held-out test set it never trained on."

---

### 0:35–1:20 · The real climb (the core — let it breathe)
**SHOW:** Terminal running `uv run python scripts/offline_demo.py` — the leaderboard climbing v1 → v4.

> "Here's a real run on a real SQLite database. Version one scores fifty percent on the held-out test. Crucible reads its own failing traces, sees the failures cluster on JOINs, and writes one atomic fix. Version two — seventy-five. Next cluster: aggregation. Then ordering. Each fix is one hypothesis, one change, re-measured. Version four: one hundred percent on held-out test. Every number you see is real SQL executed against the database and compared to human gold answers — no estimates, no mocks."

---

### 1:20–1:45 · Arize Phoenix + MCP (the partner integration)
**SHOW:** Phoenix Cloud — `app.phoenix.arize.com/s/sahuankit453`, the `crucible` project + `crucible-world-v1-train` experiment.

> "Every run is traced and scored in Arize Phoenix. And this is the key move: Crucible doesn't guess why it failed — a Gemini 3 agent reads its *own* failing experiment back out through the Phoenix MCP server, and that self-diagnosis drives the next fix. The agent observes itself."

---

### 1:45–2:00 · Product + close
**SHOW:** Back to the hosted Mission Control UI.

> "It's all live in one place — Gemini 3 for reasoning, Arize Phoenix for memory and introspection. One database in, one tuned, measured agent out. That's Crucible."

---

## Shot checklist (record in this order, then voice over)
1. Hosted UI: `https://crucible-api-md84.onrender.com` — slow pan over header + panels.
2. Terminal: run `uv run python scripts/offline_demo.py` — capture the full climb to v4 100%.
3. Phoenix: the `crucible` project + the `crucible-world-v1-train` experiment.
4. (Optional) the repo `github.com/Aankirz/Crucible` — README + the loop diagram.

## Submission (Devpost)
- Track: **Arize**
- Hosted URL: `https://crucible-api-md84.onrender.com`
- Repo: `https://github.com/Aankirz/Crucible`
- Video: this recording
