import { forwardRef, useEffect, useState } from "react";
import {
  API_BASE,
  fetchDatabases,
  type DatabaseInfo,
  type FeedSource,
  type LoopEvent,
} from "../useEvents";
import { DatabasePicker } from "./DatabasePicker";
import { SchemaViewer } from "./SchemaViewer";
import { ActivityLog } from "./ActivityLog";
import { Leaderboard } from "./Leaderboard";
import { HypothesisCard } from "./HypothesisCard";
import { PhoenixPanel } from "./PhoenixPanel";

interface ConsoleProps {
  events: LoopEvent[];
  source: FeedSource;
}

/**
 * Mission Control — the interactive core. Owns database selection and run
 * controls, and lays out the live panels (activity, leaderboard, hypothesis,
 * Phoenix). The forwarded ref lets the hero scroll here and focus the picker.
 */
export const Console = forwardRef<HTMLElement, ConsoleProps>(function Console(
  { events, source },
  ref
) {
  const [databases, setDatabases] = useState<DatabaseInfo[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [dbLoading, setDbLoading] = useState(true);
  const [dbError, setDbError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  // Load the database catalog once on mount.
  useEffect(() => {
    let cancelled = false;
    fetchDatabases()
      .then((dbs) => {
        if (cancelled) return;
        setDatabases(dbs);
        if (dbs.length > 0) setSelectedId(dbs[0].id);
      })
      .catch(() => {
        if (!cancelled) setDbError("Could not load databases. Is the backend up?");
      })
      .finally(() => {
        if (!cancelled) setDbLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // A run is "done" once run_complete arrives — re-enable the controls.
  const lastEvent = events[events.length - 1];
  useEffect(() => {
    if (lastEvent?.type === "run_complete") setRunning(false);
  }, [lastEvent]);

  const selected = databases.find((d) => d.id === selectedId) ?? null;

  const start = (autopilot: boolean) => {
    if (!selectedId) return;
    setRunning(true);
    fetch(
      `${API_BASE}/run?db_id=${encodeURIComponent(selectedId)}&autopilot=${autopilot}`,
      { method: "POST" }
    ).catch(() => {
      // Backend unreachable; the feed pill reflects the error state.
      setRunning(false);
    });
  };

  const approve = () =>
    fetch(`${API_BASE}/approve`, { method: "POST" }).catch(() => {});

  const noDb = !selectedId || databases.length === 0;

  return (
    <section className="console" ref={ref} aria-labelledby="console-heading">
      <header className="section-head">
        <span className="section-kicker">mission control</span>
        <h2 id="console-heading">Live console</h2>
        <p className="section-lede">
          Pick a database, start a run, and watch the agent draft, score,
          introspect, and mutate in real time.
        </p>
      </header>

      <div className="console-bar panel">
        <DatabasePicker
          databases={databases}
          selectedId={selectedId}
          onSelect={setSelectedId}
          loading={dbLoading}
          error={dbError}
        />

        <SchemaViewer dbId={selectedId} />

        <div className="run-controls" role="group" aria-label="Run controls">
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => start(true)}
            disabled={noDb || running}
          >
            {running ? "Running…" : "Run (autopilot)"}
          </button>
          <button
            type="button"
            className="btn"
            onClick={() => start(false)}
            disabled={noDb || running}
          >
            Run (approve gates)
          </button>
          <button type="button" className="btn btn-ghost" onClick={approve}>
            Approve / Promote
          </button>

          <span
            className={`feed-pill feed-${source}`}
            role="status"
            aria-live="polite"
          >
            <span className="feed-dot" aria-hidden="true" />
            {source === "connecting" && "Connecting…"}
            {source === "live" && "Live feed"}
            {source === "error" && "Backend waking…"}
          </span>
        </div>

        {selected && (
          <p className="console-hint">
            {selected.mode === "demo"
              ? "Demo mode streams a deterministic loop instantly — no LLM calls."
              : "Live mode runs real Gemini 3; expect each step to take longer."}
          </p>
        )}
      </div>

      <div className="console-grid">
        <div className="console-col-main">
          <ActivityLog events={events} running={running} />
        </div>
        <div className="console-col-side">
          <Leaderboard events={events} />
          <HypothesisCard events={events} />
          <PhoenixPanel events={events} />
        </div>
      </div>
    </section>
  );
});
