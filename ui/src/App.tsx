import { useMemo, useState } from "react";
import { useEvents, type LoopEvent } from "./useEvents";
import { Leaderboard } from "./components/Leaderboard";
import { HypothesisCard } from "./components/HypothesisCard";
import "./styles.css";

const API = "http://localhost:8000";

export default function App() {
  // Force the mock run via ?demo=1, or via the in-UI toggle.
  const initialDemo = useMemo(
    () => new URLSearchParams(window.location.search).has("demo"),
    []
  );
  const [forceMock, setForceMock] = useState(initialDemo);

  const { events, source, replayMock } = useEvents(forceMock);

  const promoted = events.find(
    (e): e is Extract<LoopEvent, { type: "promoted" }> => e.type === "promoted"
  );

  const isMock = source === "mock";

  const start = (autopilot: boolean) =>
    fetch(`${API}/run?autopilot=${autopilot}`, { method: "POST" }).catch(() => {
      /* offline demo: the mock feed is already running, nothing to surface */
    });

  const approve = () =>
    fetch(`${API}/approve`, { method: "POST" }).catch(() => {});

  const onRun = (autopilot: boolean) => {
    if (isMock) {
      replayMock();
    } else {
      void start(autopilot);
    }
  };

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
            {source === "mock" && "Demo feed"}
          </div>
        </header>

        <div className="controls" role="group" aria-label="Run controls">
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => onRun(true)}
          >
            {isMock ? "Replay demo run" : "Run (autopilot)"}
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
          <label className="mock-toggle">
            <input
              type="checkbox"
              checked={forceMock}
              onChange={(e) => setForceMock(e.target.checked)}
            />
            <span>Force demo</span>
          </label>
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
