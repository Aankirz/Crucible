import { useEvents, API_BASE, type LoopEvent } from "./useEvents";
import { Leaderboard } from "./components/Leaderboard";
import { HypothesisCard } from "./components/HypothesisCard";
import "./styles.css";

export default function App() {
  const { events, source } = useEvents();

  const promoted = events.find(
    (e): e is Extract<LoopEvent, { type: "promoted" }> => e.type === "promoted"
  );

  const start = (autopilot: boolean) =>
    fetch(`${API_BASE}/run?autopilot=${autopilot}`, { method: "POST" }).catch(
      () => {
        /* backend unreachable; the feed pill already reflects the error state */
      }
    );

  const approve = () =>
    fetch(`${API_BASE}/approve`, { method: "POST" }).catch(() => {});

  const onRun = (autopilot: boolean) => void start(autopilot);

  return (
    <div className="shell">
      <main className="app">
        <header className="masthead">
          <div className="brand">
            <span className="flame" aria-hidden="true" />
            <div>
              <h1>Crucible</h1>
              <p className="tagline">
                self-improving text-to-SQL · mission control
              </p>
            </div>
          </div>
          <div
            className={`feed-pill feed-${source}`}
            role="status"
            aria-live="polite"
          >
            <span className="feed-dot" aria-hidden="true" />
            {source === "connecting" && "Connecting…"}
            {source === "live" && "Live feed"}
            {source === "error" && "Backend waking…"}
          </div>
        </header>

        <div className="controls" role="group" aria-label="Run controls">
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => onRun(true)}
          >
            Run (autopilot)
          </button>
          <button
            type="button"
            className="btn"
            onClick={() => onRun(false)}
          >
            Run (approve gates)
          </button>
          <button type="button" className="btn" onClick={approve}>
            Approve / Promote
          </button>
        </div>

        <div className="grid">
          <HypothesisCard events={events} />
          <Leaderboard events={events} />
        </div>

        {promoted && (
          <aside className="promoted" role="status">
            <span className="promoted-icon" aria-hidden="true">
              ✓
            </span>
            <div className="promoted-text">
              <strong>Promoted v{promoted.version}</strong>
              <span className="promoted-score">
                {Math.round(promoted.test * 100)}% on held-out test
              </span>
            </div>
          </aside>
        )}
      </main>
    </div>
  );
}
