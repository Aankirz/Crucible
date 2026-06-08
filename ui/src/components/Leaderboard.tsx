import type { LoopEvent } from "../useEvents";

type VersionRow = Extract<LoopEvent, { type: "version" }>;

const pct = (n: number) => `${Math.round(n * 100)}%`;

/**
 * One row per `version` event. Test % (held-out) is the hero number and is
 * rendered with an at-a-glance climbing meter so the score-climb is felt, not read.
 */
export function Leaderboard({ events }: { events: LoopEvent[] }) {
  const versions = events.filter(
    (e): e is VersionRow => e.type === "version"
  );
  const rejected = new Set(
    events.filter((e) => e.type === "rejected").map((e) => (e as Extract<LoopEvent, { type: "rejected" }>).version)
  );

  const best = versions.reduce((m, v) => Math.max(m, v.test), 0);
  const leaderVersion = versions.find((v) => v.test === best)?.version;

  return (
    <section className="panel leaderboard-panel" aria-labelledby="lb-heading">
      <header className="panel-head">
        <h2 id="lb-heading">Leaderboard</h2>
        <span className="panel-sub">held-out test score per version</span>
      </header>

      {versions.length === 0 ? (
        <p className="empty">Awaiting first scored version…</p>
      ) : (
        <table className="leaderboard">
          <thead>
            <tr>
              <th scope="col">Version</th>
              <th scope="col">Train</th>
              <th scope="col" className="hero-col">
                Test <span className="held-out">held-out</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {versions.map((v) => {
              const isLeader = v.version === leaderVersion;
              return (
                <tr
                  key={v.version}
                  className={isLeader ? "row leader" : "row"}
                >
                  <td className="ver-cell">
                    <span className="ver-badge">v{v.version}</span>
                    {isLeader && <span className="leader-tag">leader</span>}
                  </td>
                  <td className="train-cell">{pct(v.train)}</td>
                  <td className="test-cell">
                    <div className="test-stack">
                      <strong className="test-num">{pct(v.test)}</strong>
                      <span
                        className="meter"
                        role="img"
                        aria-label={`Test score ${pct(v.test)}`}
                      >
                        <span
                          className="meter-fill"
                          style={{ width: `${Math.round(v.test * 100)}%` }}
                        />
                      </span>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}

      {rejected.size > 0 && (
        <p className="rejected-note">
          {[...rejected]
            .sort((a, b) => a - b)
            .map((v) => `v${v}`)
            .join(", ")}{" "}
          reverted (no train-score gain)
        </p>
      )}
    </section>
  );
}
