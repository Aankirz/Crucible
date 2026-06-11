# Deploying Crucible (live)

Two services, both real and live:

- **Backend** (FastAPI loop server) → **Render** (Docker, persistent process for SSE + the `npx` Phoenix MCP subprocess).
- **Frontend** (React/Vite Mission Control) → **Vercel** (static), pointed at the Render URL.

With no Spider/BIRD data configured, the backend runs the **real loop on the bundled `world` database** (real schema + human-authored gold SQL) driven by **live Gemini 3** and traced to **Arize Phoenix**. Nothing is mocked.

---

## 1. Enable reliable Gemini (the one true gate)

A live climb is dozens of Gemini calls; the free tier (20/day + 503s) cannot sustain it. Enable billing, then pick ONE credential path:

- **Path A — billing-enabled AI Studio key (simplest on a server):**
  Enable billing on your Google AI Studio / Cloud project, then use that `GOOGLE_API_KEY`. One env var, no files. Lets you use `gemini-3-pro-preview`.
- **Path B — Vertex AI:** set `GOOGLE_GENAI_USE_VERTEXAI=true`, `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION=us-central1`, and upload a service-account JSON as a Render **Secret File**, then set `GOOGLE_APPLICATION_CREDENTIALS=/etc/secrets/sa.json`.

> Path A is recommended for the Render deploy — fewer moving parts.

## 2. Deploy the backend to Render

1. Push this repo to GitHub (done by the build process).
2. Render → **New +** → **Blueprint** → connect this repo. Render reads `render.yaml`.
3. Fill the `sync: false` env vars in the dashboard:
   - `GOOGLE_API_KEY` (or the Vertex set from Path B)
   - `PHOENIX_API_KEY`
   - `PHOENIX_COLLECTOR_ENDPOINT` = `https://app.phoenix.arize.com/s/sahuankit453`
   - (`GEMINI_MODEL` and `PHOENIX_PROJECT_NAME` are preset in `render.yaml`.)
4. Deploy. Note the service URL, e.g. `https://crucible-api.onrender.com`.
5. Sanity check: open `https://<service>/healthz` → `{"ok": true, "dataset": "world", ...}`.

> Free tier spins down when idle and cold-starts (~50s) on the next hit. The UI shows **"Backend waking…"** during that window, then flips to **Live feed**.

## 3. Deploy the frontend to Vercel

1. Vercel → **Add New Project** → import this repo.
2. **Root Directory** = `ui`. Framework preset auto-detects **Vite**.
3. Add an environment variable:
   - `VITE_API_URL` = the Render service URL from step 2 (e.g. `https://crucible-api.onrender.com`).
4. Deploy. The Vercel URL is your submission's **hosted Project URL**.

> `ui/vercel.json` already sets the build/output and an SPA rewrite. CORS on the backend is permissive (`allow_origins=["*"]`), so the cross-origin SSE works.

## 4. Verify end-to-end

1. Open the Vercel URL. The feed pill should reach **Live feed** (after any cold start).
2. Click **Run (autopilot)**. Watch the leaderboard climb as real Gemini 3 drafts/scores SQL and the agent reads its own failing traces from Phoenix via MCP.
3. Confirm traces/experiments appear in your Phoenix space (`crucible` project).

## Local dev

```bash
# backend (world mode auto-activates with no Spider data)
uv run uvicorn crucible.server.app:app --reload
# frontend (defaults to http://localhost:8000)
cd ui && npm run dev
```
