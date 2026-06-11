import type { LoopEvent } from "../useEvents";

type ItemEvent = Extract<LoopEvent, { type: "item" }>;

/**
 * One scored question: the natural-language question → the generated SQL
 * (monospace) → a ✓/✗ match badge. This is the "watch it think" unit.
 */
export function ItemCard({ item }: { item: ItemEvent }) {
  const matched = item.is_match;
  return (
    <li className={matched ? "item-card matched" : "item-card missed"}>
      <div className="item-head">
        <span className="item-split">{item.split}</span>
        <span className="item-question">{item.question}</span>
        <span
          className={matched ? "item-badge ok" : "item-badge no"}
          aria-label={matched ? "matches gold SQL" : "does not match gold SQL"}
        >
          {matched ? "✓" : "✗"}
        </span>
      </div>
      <pre className="item-sql">
        <code>{item.predicted_sql}</code>
      </pre>
      {item.error && <p className="item-error">{item.error}</p>}
    </li>
  );
}
