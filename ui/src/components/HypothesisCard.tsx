import type { LoopEvent } from "../useEvents";

type Hypothesis = Extract<LoopEvent, { type: "hypothesis" }>;

const PLACEHOLDER = "Analyzing own traces via Phoenix MCP…";

/**
 * Shows the agent's latest diagnosis: the dominant failure category and its
 * natural-language read of its own failing traces. Always rendered so the
 * "what is it thinking" slot is stable on screen, even before the first event.
 */
export function HypothesisCard({ events }: { events: LoopEvent[] }) {
  const last = [...events]
    .reverse()
    .find((e): e is Hypothesis => e.type === "hypothesis");

  const category = last?.category ?? "diagnosing";
  const summary = last?.mcp_summary || PLACEHOLDER;
  const thinking = !last;

  return (
    <section
      className={thinking ? "panel hypothesis thinking" : "panel hypothesis"}
      aria-labelledby="hyp-heading"
      aria-live="polite"
    >
      <header className="panel-head">
        <h2 id="hyp-heading">Current hypothesis</h2>
        <span className="panel-sub">self-diagnosis via MCP</span>
      </header>
      <div className="hypothesis-body">
        <span className="tag" data-category={category}>
          {category}
        </span>
        <p className="hypothesis-text">{summary}</p>
      </div>
    </section>
  );
}
