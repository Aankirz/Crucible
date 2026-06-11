import type { LoopEvent } from "../useEvents";

type PhoenixEvent = Extract<LoopEvent, { type: "phoenix" }>;

/**
 * Lists the experiments logged to Arize Phoenix as `phoenix` events arrive.
 * Each links into the Phoenix space (new tab) when a url is present; if the
 * url is "", the experiment name is shown without a link.
 */
export function PhoenixPanel({ events }: { events: LoopEvent[] }) {
  const phoenix = events.filter(
    (e): e is PhoenixEvent => e.type === "phoenix"
  );

  return (
    <section className="panel phoenix-panel" aria-labelledby="phx-heading">
      <header className="panel-head">
        <h2 id="phx-heading">Traced in Arize Phoenix</h2>
        <span className="panel-sub">logged experiments</span>
      </header>

      {phoenix.length === 0 ? (
        <p className="empty">No experiments logged yet.</p>
      ) : (
        <ul className="phoenix-list">
          {phoenix.map((p, i) => (
            <li key={`${p.experiment}-${i}`} className="phoenix-row">
              <span className="phoenix-icon" aria-hidden="true">
                ◎
              </span>
              <div className="phoenix-meta">
                {p.url ? (
                  <a
                    className="phoenix-link"
                    href={p.url}
                    target="_blank"
                    rel="noreferrer noopener"
                  >
                    {p.experiment}
                    <span className="phoenix-ext" aria-hidden="true">
                      ↗
                    </span>
                  </a>
                ) : (
                  <span className="phoenix-name">{p.experiment}</span>
                )}
                <span className="phoenix-tags">
                  <span className="phoenix-split">{p.split}</span>
                  <span className="phoenix-ver">v{p.version}</span>
                </span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
