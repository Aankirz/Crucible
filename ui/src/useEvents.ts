import { useEffect, useRef, useState } from "react";

/**
 * FROZEN event contract — must match src/crucible/server/events.py exactly.
 * Scores are 0..1. `test` is the held-out headline number.
 */
export type LoopEvent =
  | { type: "version"; version: number; train: number; test: number }
  | { type: "hypothesis"; category: string; mcp_summary: string }
  | { type: "rejected"; version: number }
  | { type: "promoted"; version: number; test: number }
  | { type: "error"; message: string };

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
      try {
        const parsed = JSON.parse(m.data) as LoopEvent;
        if (!gotLiveEvent.current) {
          gotLiveEvent.current = true;
        }
        setSource("live");
        setEvents((prev) => [...prev, parsed]);
      } catch {
        // Ignore malformed frames; never let a bad event crash the feed.
      }
    };

    es.onopen = () => {
      // Connection up; remain "connecting" until the first event proves the
      // stream is flowing, unless we've already seen live data.
      if (!gotLiveEvent.current) setSource("connecting");
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
