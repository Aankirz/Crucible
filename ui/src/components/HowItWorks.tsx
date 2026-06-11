interface Step {
  n: string;
  title: string;
  body: string;
  glyph: string;
}

const STEPS: Step[] = [
  {
    n: "01",
    title: "Draft an agent",
    glyph: "✎",
    body: "Crucible writes a first text-to-SQL agent for the chosen schema — a candidate version 1.",
  },
  {
    n: "02",
    title: "Score on real SQL",
    glyph: "≣",
    body: "Each question is answered and the predicted SQL is executed against the real database, then matched against human gold SQL. No proxy metrics.",
  },
  {
    n: "03",
    title: "Introspect via Phoenix",
    glyph: "◎",
    body: "It reads its own failing traces through the Arize Phoenix MCP server — clustering the questions it got wrong.",
  },
  {
    n: "04",
    title: "Hypothesize",
    glyph: "✶",
    body: "The dominant failure cluster becomes a natural-language self-diagnosis: a concrete theory about why it is losing points.",
  },
  {
    n: "05",
    title: "Mutate & re-score",
    glyph: "⟳",
    body: "It edits the agent to fix the hypothesis, re-scores, and keeps the change only if held-out test improves. Otherwise it reverts.",
  },
  {
    n: "06",
    title: "Clear the bar",
    glyph: "▲",
    body: "Accepted versions stack on the leaderboard. A representative run climbs held-out test from ~50% to 100% over a handful of mutations.",
  },
];

/**
 * The reflexive loop explained in six tight steps, with the real headline
 * result called out. Semantic ordered list under the hood.
 */
export function HowItWorks() {
  return (
    <section className="how" aria-labelledby="how-heading">
      <header className="section-head">
        <span className="section-kicker">the reflexive loop</span>
        <h2 id="how-heading">How Crucible improves itself</h2>
        <p className="section-lede">
          A closed loop that measures, diagnoses, and mutates — then proves the
          gain on data it never trained on.
        </p>
      </header>

      <ol className="how-grid">
        {STEPS.map((step) => (
          <li key={step.n} className="how-card">
            <div className="how-card-top">
              <span className="how-num">{step.n}</span>
              <span className="how-glyph" aria-hidden="true">
                {step.glyph}
              </span>
            </div>
            <h3>{step.title}</h3>
            <p>{step.body}</p>
          </li>
        ))}
      </ol>
    </section>
  );
}
