import { useEffect, useRef } from "react";
import type { LoopEvent, StatusPhase } from "../useEvents";
import { ItemCard } from "./ItemCard";

type StatusEvent = Extract<LoopEvent, { type: "status" }>;
type ItemEvent = Extract<LoopEvent, { type: "item" }>;

/** A line in the activity log: either a phase banner or a scored item. */
type Entry =
  | { kind: "status"; key: string; event: StatusEvent }
  | { kind: "item"; key: string; event: ItemEvent };

const PHASE_LABEL: Record<StatusPhase, string> = {
  start: "Start",
  scoring: "Scoring",
  introspecting: "Introspecting",
  mutating: "Mutating",
  accepted: "Accepted",
  rejected: "Rejected",
  promoting: "Promoting",
  done: "Done",
};

interface ActivityLogProps {
  events: LoopEvent[];
  running: boolean;
}

/**
 * Step-by-step activity log. Interleaves `status` phase banners with `item`
 * cards in arrival order so the run reads top-to-bottom like a live trace.
 * Auto-scrolls to the newest entry while the run is active.
 */
export function ActivityLog({ events, running }: ActivityLogProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  const entries: Entry[] = events.flatMap((e, i): Entry[] => {
    if (e.type === "status")
      return [{ kind: "status", key: `s${i}`, event: e }];
    if (e.type === "item") return [{ kind: "item", key: `i${i}`, event: e }];
    return [];
  });

  useEffect(() => {
    const el = scrollRef.current;
    if (el && running) el.scrollTop = el.scrollHeight;
  }, [entries.length, running]);

  return (
    <section className="panel activity-panel" aria-labelledby="act-heading">
      <header className="panel-head">
        <h2 id="act-heading">Activity</h2>
        <span className="panel-sub">step-by-step · watch it think</span>
      </header>

      {entries.length === 0 ? (
        <p className="empty">
          {running
            ? "Booting the loop…"
            : "Pick a database and start a run to watch each step stream in."}
        </p>
      ) : (
        <div className="activity-scroll" ref={scrollRef} aria-live="polite">
          <ol className="activity-list">
            {entries.map((entry) =>
              entry.kind === "status" ? (
                <li
                  key={entry.key}
                  className={`status-line phase-${entry.event.phase}`}
                >
                  <span className="status-phase">
                    {PHASE_LABEL[entry.event.phase] ?? entry.event.phase}
                  </span>
                  <span className="status-msg">{entry.event.message}</span>
                </li>
              ) : (
                <ItemCard key={entry.key} item={entry.event} />
              )
            )}
          </ol>
        </div>
      )}
    </section>
  );
}
