# Crucible — Frontend/Backend Contract (v2: landing page + multi-DB + step-by-step)

This is the FROZEN seam between the backend (`src/`, `scripts/`, `tests/`) and the
frontend (`ui/`). Both sides code against exactly this. Do not change it without
updating both sides.

## REST endpoints

### `GET /databases`
Returns the catalog of bundled databases the user can pick in the dropdown.
```json
{
  "databases": [
    {
      "id": "world",
      "name": "World — countries, cities, languages",
      "domain": "geography",
      "tables": ["country", "city", "countrylanguage"],
      "num_questions": 10,
      "mode": "demo",          // "demo" = deterministic instant; "live" = real Gemini
      "blurb": "A compact geography database. Instant deterministic demo."
    }
  ]
}
```

### `GET /schema?db_id=<id>`
Returns the DDL for a database (so the UI can show the schema).
```json
{ "db_id": "world", "schema": "CREATE TABLE country (...); ..." }
```

### `POST /run?db_id=<id>&autopilot=true`
Starts an optimization run for the chosen database in a background thread.
Returns `{ "started": true, "db_id": "...", "mode": "demo"|"live" }` or
`{ "started": false, "reason": "..." }` if a run is already in progress.

### `POST /approve`
Releases the human-approval gate. Returns `{ "ok": true }`.

### `GET /healthz`
`{ "ok": true, "service": "crucible-mission-control", "dataset": "...", "running": bool }`

### `GET /events`  (Server-Sent Events)
Streams JSON objects (one per `data:` frame). Event types below. The frontend
must tolerate unknown event types (ignore them) for forward-compatibility.

## SSE event types (FROZEN)

Existing (keep working):
```ts
| { type: "version";   version: number; train: number; test: number }   // scores 0..1
| { type: "hypothesis"; category: string; mcp_summary: string }
| { type: "rejected";  version: number }
| { type: "promoted";  version: number; test: number }
| { type: "error";     message: string }
```

NEW (richer step-by-step + Phoenix visibility):
```ts
// Human-readable step the loop is on, for a live activity log.
| { type: "status"; phase: string; message: string }
//   phase ∈ "start" | "scoring" | "introspecting" | "mutating" | "accepted" | "rejected" | "promoting" | "done"

// One scored question — lets the UI show each generated SQL as it happens.
| { type: "item";
    version: number;
    split: "train" | "test";
    question: string;
    predicted_sql: string;
    is_match: boolean;
    error?: string | null }

// A Phoenix experiment was logged — the UI shows it + a clickable link.
| { type: "phoenix";
    experiment: string;
    url: string;          // deep link into the Phoenix space (may be "" if unavailable)
    split: "train" | "test";
    version: number }

// Final run summary.
| { type: "run_complete"; best_version: number; best_test: number; db_id: string }
```

## Ordering guarantee
For each run: `status(start)` → per version: `status(scoring)` → several `item` →
`version` → `phoenix` (best-effort) → `status(introspecting)` → `hypothesis` →
`status(mutating)` → (`version`+`item`s on accept | `rejected`) … →
`status(promoting)` → `promoted` → `run_complete`.
The UI must not assume every optional event appears (e.g. `phoenix` is best-effort).

## Notes
- `demo` mode databases stream the deterministic loop (instant, no LLM). `live`
  mode databases use real Gemini 3 (slower). The UI shows the mode per database.
- All scores are floats 0..1. `predicted_sql` is the raw model SQL (may be long).
