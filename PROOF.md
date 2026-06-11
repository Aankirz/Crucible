# Crucible — verified live end-to-end (2026-06-12)

Real Gemini 3 (Vertex AI, drawing Google Cloud credits) + real Arize Phoenix +
real MCP self-introspection. Every layer below ran live, not mocked.

## 1. Live Gemini 3 climb on Vertex
`scripts/live_gemini_demo.py` (Vertex, gemini-3-flash-preview, location=global):

```
v1 | train   0.0% | test 75.0%   -> agent has no schema; fails
v2 | train 100.0% | test 75.0%   -> learned the schema from its own failures
```
The agent earns the schema from its failures — an honest climb on real SQL.

## 2. Full Phoenix + MCP introspection (the Arize-track money shot)
`scripts/phoenix_e2e.py`:

```
[1-2] v1 scored 40% on real SQL — 3 failing (JOIN, GROUP BY, ORDER BY)
[3]   Logged real experiment to Phoenix Cloud: crucible-world-v1-train
[4]   Gemini 3 agent introspected its OWN failures via the Phoenix MCP server:
      FAILURE: "The model consistently omits necessary SQL clauses such as
                JOIN, GROUP BY, and ORDER BY, resulting in simplified but
                incorrect queries."
      SCORE: execution_match = 0.4
RESULT: live MCP introspection OK
```

The agent's self-diagnosis is correct (the failing clusters really are JOIN /
GROUP BY / ORDER BY) and the score it read back (0.4) matches the real score.

## How it's wired
- **Model:** Vertex AI, `GOOGLE_GENAI_USE_VERTEXAI=true`,
  `GOOGLE_CLOUD_PROJECT=gen-lang-client-0589427141`, `GOOGLE_CLOUD_LOCATION=global`,
  `GEMINI_MODEL=gemini-3-flash-preview`. Auth via ADC (aankir101@gmail.com).
  Vertex draws the Google Cloud trial credits (the AI-Studio prepay key cannot).
- **Phoenix:** `PHOENIX_COLLECTOR_ENDPOINT=https://app.phoenix.arize.com/s/sahuankit453`,
  project `crucible`.
- **MCP:** `@arizeai/phoenix-mcp` launched via npx; a Google ADK (Gemini) agent
  reads the logged experiment back and reports the dominant failure pattern.

## Reproduce
```bash
# real live climb
uv run python scripts/live_gemini_demo.py
# full Phoenix + MCP introspection
uv run python scripts/phoenix_e2e.py
# deterministic, no-credentials climb (50% -> 100%)
uv run python scripts/offline_demo.py
```
