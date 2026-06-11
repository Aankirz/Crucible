import { LoopDiagram } from "./LoopDiagram";

interface HeroProps {
  /** Scroll to the live console and focus its first control. */
  onRunDemo: () => void;
  /** Scroll to the "bring your own database" guide. */
  onUseOwn: () => void;
}

/**
 * Landing hero. Strong typographic hierarchy with the product one-liner, the
 * reflexive-loop subcopy, two CTAs, and a compact loop visual.
 */
export function Hero({ onRunDemo, onUseOwn }: HeroProps) {
  return (
    <section className="hero" aria-labelledby="hero-heading">
      <div className="hero-copy">
        <p className="hero-eyebrow">
          <span className="flame flame-sm" aria-hidden="true" />
          self-improving text-to-SQL · mission control
        </p>

        <h1 id="hero-heading" className="hero-headline">
          One database in → one tuned, measured
          <span className="hero-accent"> text-to-SQL agent</span> out.
        </h1>

        <p className="hero-sub">
          Crucible drafts a text-to-SQL agent, scores it against human gold SQL,
          reads its own failing traces through the Arize Phoenix MCP server, and
          self-improves — mutation by mutation — until it clears a real quality
          bar. Every score is real SQL executed against a real database.
        </p>

        <div className="hero-cta">
          <button type="button" className="btn btn-primary" onClick={onRunDemo}>
            Run a live demo
            <span className="btn-arrow" aria-hidden="true">
              ↓
            </span>
          </button>
          <button type="button" className="btn btn-ghost" onClick={onUseOwn}>
            Use your own database
          </button>
        </div>

        <dl className="hero-stats">
          <div>
            <dt>held-out test</dt>
            <dd>
              ~50% <span aria-hidden="true">→</span> 100%
            </dd>
          </div>
          <div>
            <dt>scoring</dt>
            <dd>real SQL · real DB</dd>
          </div>
          <div>
            <dt>introspection</dt>
            <dd>Phoenix MCP</dd>
          </div>
        </dl>
      </div>

      <div className="hero-visual">
        <LoopDiagram />
      </div>
    </section>
  );
}
