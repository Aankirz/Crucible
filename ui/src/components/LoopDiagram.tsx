const STEPS = [
  { id: "draft", label: "Draft" },
  { id: "score", label: "Score" },
  { id: "introspect", label: "Introspect" },
  { id: "hypothesize", label: "Hypothesize" },
  { id: "mutate", label: "Mutate" },
  { id: "rescore", label: "Re-score" },
] as const;

/**
 * Compact visual of the reflexive loop. Pure CSS/SVG — no animation libraries.
 * Nodes sit on a ring; a rotating accent arc conveys the "always looping" idea
 * (transform-only, paused under prefers-reduced-motion via CSS).
 */
export function LoopDiagram() {
  const radius = 132;
  const cx = 160;
  const cy = 160;

  const points = STEPS.map((step, i) => {
    const angle = (i / STEPS.length) * Math.PI * 2 - Math.PI / 2;
    return {
      ...step,
      x: cx + radius * Math.cos(angle),
      y: cy + radius * Math.sin(angle),
    };
  });

  return (
    <div className="loop-diagram" aria-hidden="true">
      <svg viewBox="0 0 320 320" role="presentation">
        <defs>
          <linearGradient id="loop-arc" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="oklch(70% 0.18 35)" />
            <stop offset="100%" stopColor="oklch(74% 0.15 250)" />
          </linearGradient>
        </defs>

        <circle
          className="loop-ring"
          cx={cx}
          cy={cy}
          r={radius}
          fill="none"
        />
        <circle
          className="loop-arc"
          cx={cx}
          cy={cy}
          r={radius}
          fill="none"
          stroke="url(#loop-arc)"
          strokeLinecap="round"
        />

        {points.map((p) => (
          <g key={p.id} className="loop-node">
            <circle cx={p.x} cy={p.y} r={7} />
            <text
              x={p.x}
              y={p.y < cy ? p.y - 14 : p.y + 22}
              textAnchor="middle"
            >
              {p.label}
            </text>
          </g>
        ))}

        <g className="loop-core">
          <circle cx={cx} cy={cy} r={30} />
          <text x={cx} y={cy - 2} textAnchor="middle" className="loop-core-top">
            self
          </text>
          <text
            x={cx}
            y={cy + 12}
            textAnchor="middle"
            className="loop-core-bottom"
          >
            improving
          </text>
        </g>
      </svg>
    </div>
  );
}
