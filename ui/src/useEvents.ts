import { useCallback, useEffect, useRef, useState } from "react";

/**
 * FROZEN event contract — must match src/crucible/server/events.py exactly.
 * Scores are 0..1. `test` is the held-out headline number.
 */
export type LoopEvent =
  | { type: "version"; version: number; train: number; test: number }
  | { type: "hypothesis"; category: string; mcp_summary: string }
  | { type: "rejected"; version: number }
  | { type: "promoted"; version: number; test: number };

const SSE_URL = "http://localhost:8000/events";

/** How the event feed is currently sourced. */
export type FeedSource = "connecting" | "live" | "mock";

/**
 * A realistic climbing run used when no backend is present, or when the demo
 * mode is forced. Mirrors the contract ordering: version -> hypothesis ->
 * (rejected) -> version ... -> promoted.
 */
const MOCK_SCRIPT: { delay: number; event: LoopEvent }[] = [
  {
    delay: 600,
    event: {
      type: "hypothesis",
      category: "join",
      mcp_summary:
        "Phoenix MCP traces show 6/12 failures stem from missing JOINs across foreign keys. Baseline ignores relational structure.",
    },
  },
  { delay: 1100, event: { type: "version", version: 1, train: 0.61, test: 0.58 } },
  {
    delay: 1100,
    event: {
      type: "hypothesis",
      category: "aggregation",
      mcp_summary:
        "Remaining errors cluster on GROUP BY / HAVING. Adding aggregation few-shot exemplars to the prompt.",
    },
  },
  { delay: 1100, event: { type: "version", version: 2, train: 0.74, test: 0.71 } },
  { delay: 900, event: { type: "rejected", version: 3 } },
  {
    delay: 1000,
    event: {
      type: "hypothesis",
      category: "subquery",
      mcp_summary:
        "Reverted the over-fit schema dump. Correlated subqueries are the last failing cluster — injecting a targeted decomposition rule.",
    },
  },
  { delay: 1200, event: { type: "version", version: 4, train: 0.91, test: 0.88 } },
  { delay: 900, event: { type: "promoted", version: 4, test: 0.88 } },
];

/**
 * Subscribes to the live SSE feed and accumulates typed events.
 *
 * Resolution order:
 *   1. Default to live SSE at {@link SSE_URL}.
 *   2. If the connection errors before any event arrives, fall back to the mock run.
 *   3. `forceMock` (e.g. ?demo=1) always replays the mock run, never touching the network.
 */
export function useEvents(forceMock: boolean): {
  events: LoopEvent[];
  source: FeedSource;
  replayMock: () => void;
} {
  const [events, setEvents] = useState<LoopEvent[]>([]);
  const [source, setSource] = useState<FeedSource>("connecting");
  const timers = useRef<number[]>([]);
  const gotLiveEvent = useRef(false);

  const clearTimers = useCallback(() => {
    timers.current.forEach((id) => window.clearTimeout(id));
    timers.current = [];
  }, []);

  const runMock = useCallback(() => {
    clearTimers();
    setEvents([]);
    setSource("mock");
    let cumulative = 0;
    MOCK_SCRIPT.forEach(({ delay, event }) => {
      cumulative += delay;
      const id = window.setTimeout(() => {
        setEvents((prev) => [...prev, event]);
      }, cumulative);
      timers.current.push(id);
    });
  }, [clearTimers]);

  useEffect(() => {
    if (forceMock) {
      runMock();
      return clearTimers;
    }

    let es: EventSource | null = null;
    try {
      es = new EventSource(SSE_URL);
    } catch {
      runMock();
      return clearTimers;
    }

    es.onmessage = (m) => {
      try {
        const parsed = JSON.parse(m.data) as LoopEvent;
        if (!gotLiveEvent.current) {
          gotLiveEvent.current = true;
          setSource("live");
        }
        setEvents((prev) => [...prev, parsed]);
      } catch {
        // Ignore malformed frames; never let a bad event crash the feed.
      }
    };

    es.onerror = () => {
      // Only fall back if we never received a real event — a live run that
      // simply ended should not be clobbered by the mock.
      if (!gotLiveEvent.current) {
        es?.close();
        runMock();
      }
    };

    return () => {
      es?.close();
      clearTimers();
    };
  }, [forceMock, runMock, clearTimers]);

  return { events, source, replayMock: runMock };
}
