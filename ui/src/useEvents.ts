import { useEffect, useRef, useState } from "react";

/**
 * FROZEN event contract — must match src/crucible/server/events.py exactly.
 * Scores are 0..1. `test` is the held-out headline number.
 *
 * The union below mirrors docs/UI_API_CONTRACT.md. The UI must tolerate unknown
 * event types (ignore them) for forward-compatibility.
 */
export type LoopEvent =
  | { type: "version"; version: number; train: number; test: number }
  | { type: "hypothesis"; category: string; mcp_summary: string }
  | { type: "rejected"; version: number }
  | { type: "promoted"; version: number; test: number }
  | { type: "error"; message: string }
  | { type: "status"; phase: StatusPhase; message: string }
  | {
      type: "item";
      version: number;
      split: Split;
      question: string;
      predicted_sql: string;
      is_match: boolean;
      error?: string | null;
    }
  | {
      type: "phoenix";
      experiment: string;
      url: string;
      split: Split;
      version: number;
    }
  | {
      type: "run_complete";
      best_version: number;
      best_test: number;
      db_id: string;
    };

export type Split = "train" | "test";

export type StatusPhase =
  | "start"
  | "scoring"
  | "introspecting"
  | "mutating"
  | "accepted"
  | "rejected"
  | "promoting"
  | "done";

/** A bundled database the user can pick in the console. */
export interface DatabaseInfo {
  id: string;
  name: string;
  domain: string;
  tables: string[];
  num_questions: number;
  mode: "demo" | "live";
  blurb: string;
}

/**
 * Backend base URL. Set VITE_API_URL at build time (e.g. the Render service URL)
 * for the deployed UI; falls back to the local dev server otherwise. No mock or
 * replay path — the UI reflects only the real live backend.
 */
// VITE_API_URL unset -> local dev backend. Set to "" for a same-origin
// single-service deploy (FastAPI serves this bundle), or to the backend URL when
// the UI is hosted separately.
export const API_BASE: string = (() => {
  const v = import.meta.env.VITE_API_URL as string | undefined;
  if (v === undefined) return "http://localhost:8000";
  return v.replace(/\/$/, "");
})();

const SSE_URL = `${API_BASE}/events`;

/** How the event feed is currently sourced. */
export type FeedSource = "connecting" | "live" | "error";

/**
 * Subscribes to the live SSE feed and accumulates typed events.
 *
 * The browser's EventSource reconnects on its own after transient drops (e.g. a
 * free-tier backend cold-starting). We surface "connecting" until the first real
 * event arrives, "live" once it does, and "error" if the connection fails before
 * any event — while leaving the socket open so it recovers automatically.
 */
export function useEvents(): {
  events: LoopEvent[];
  source: FeedSource;
} {
  const [events, setEvents] = useState<LoopEvent[]>([]);
  const [source, setSource] = useState<FeedSource>("connecting");
  const gotLiveEvent = useRef(false);

  useEffect(() => {
    let es: EventSource | null = null;
    try {
      es = new EventSource(SSE_URL);
    } catch {
      setSource("error");
      return;
    }

    es.onmessage = (m) => {
      const parsed = parseEvent(m.data);
      if (parsed === null) return; // ignore malformed / unknown frames
      if (!gotLiveEvent.current) {
        gotLiveEvent.current = true;
      }
      setSource("live");
      setEvents((prev) => [...prev, parsed]);
    };

    es.onopen = () => {
      // Connection established — reflect the live backend immediately (idle until
      // a run streams events), rather than sitting on "connecting" forever.
      setSource("live");
    };

    es.onerror = () => {
      // Reflect the failure but keep the socket open so EventSource retries
      // (the backend may be cold-starting). A live run that simply ended is not
      // clobbered because gotLiveEvent stays true.
      if (!gotLiveEvent.current) setSource("error");
    };

    return () => {
      es?.close();
    };
  }, []);

  return { events, source };
}

/**
 * Parse a raw SSE frame into a known LoopEvent, or null if it is malformed or
 * an unknown event type. Narrowing from `unknown` keeps app code `any`-free.
 */
function parseEvent(raw: string): LoopEvent | null {
  let data: unknown;
  try {
    data = JSON.parse(raw);
  } catch {
    return null;
  }
  if (typeof data !== "object" || data === null) return null;
  const ev = data as Record<string, unknown>;
  // We trust the frozen contract for shape per `type`; only the discriminant is
  // checked so unknown event types are silently ignored.
  if (typeof ev.type !== "string") return null;
  const KNOWN = new Set([
    "version",
    "hypothesis",
    "rejected",
    "promoted",
    "error",
    "status",
    "item",
    "phoenix",
    "run_complete",
  ]);
  if (!KNOWN.has(ev.type)) return null;
  return data as LoopEvent;
}

/** Shape returned by GET /databases. */
interface DatabasesResponse {
  databases: DatabaseInfo[];
}

/** Shape returned by GET /schema?db_id=. */
interface SchemaResponse {
  db_id: string;
  schema: string;
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) {
    throw new Error(`Request failed: ${res.status} ${res.statusText}`);
  }
  return (await res.json()) as T;
}

/** Fetch the catalog of bundled databases for the picker. */
export async function fetchDatabases(): Promise<DatabaseInfo[]> {
  const data = await getJson<DatabasesResponse>("/databases");
  return Array.isArray(data.databases) ? data.databases : [];
}

/** Fetch the DDL for a database. */
export async function fetchSchema(dbId: string): Promise<string> {
  const data = await getJson<SchemaResponse>(
    `/schema?db_id=${encodeURIComponent(dbId)}`
  );
  return data.schema ?? "";
}
