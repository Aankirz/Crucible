import { forwardRef } from "react";
import { CopyBlock } from "./CopyBlock";

const REPO_URL = "https://github.com/Aankirz/Crucible";

interface GuideStep {
  n: string;
  title: string;
  body: string;
  code?: string;
  codeLabel?: string;
}

const STEPS: GuideStep[] = [
  {
    n: "1",
    title: "Clone the repo",
    body: "Grab Crucible and step into it.",
    codeLabel: "clone",
    code: `git clone ${REPO_URL}\ncd Crucible`,
  },
  {
    n: "2",
    title: "Install dependencies",
    body: "Crucible uses uv for a fast, reproducible environment.",
    codeLabel: "install",
    code: "uv sync",
  },
  {
    n: "3",
    title: "Point at your SQLite database",
    body: "Set CRUCIBLE_DB_PATH to your own .sqlite file. Crucible reads the schema directly from it.",
    codeLabel: "configure",
    code: 'export CRUCIBLE_DB_PATH="/path/to/your.sqlite"',
  },
  {
    n: "4",
    title: "Provide gold questions",
    body: "Supply your evaluation set — natural-language questions paired with the human gold SQL Crucible scores against. This is how every score stays real.",
  },
  {
    n: "5",
    title: "Run Crucible",
    body: "Kick off the loop and watch it draft, score, introspect, and self-improve on your data.",
    codeLabel: "run",
    code: "uv run crucible",
  },
];

/**
 * "Bring your own database" guide. Honest about the local-only path: there is
 * no in-browser upload — a judge runs Crucible against their own SQLite
 * locally. Forwarded ref lets the hero's secondary CTA scroll here.
 */
export const ByoGuide = forwardRef<HTMLElement>(function ByoGuide(_props, ref) {
  return (
    <section className="byo" ref={ref} aria-labelledby="byo-heading">
      <header className="section-head">
        <span className="section-kicker">run it yourself</span>
        <h2 id="byo-heading">Bring your own database</h2>
        <p className="section-lede">
          Point Crucible at your own SQLite and gold questions, locally. In-browser
          upload is not supported — this is the real, reproducible local path.
        </p>
      </header>

      <ol className="byo-steps">
        {STEPS.map((step) => (
          <li key={step.n} className="byo-step">
            <span className="byo-num" aria-hidden="true">
              {step.n}
            </span>
            <div className="byo-step-body">
              <h3>{step.title}</h3>
              <p>{step.body}</p>
              {step.code && <CopyBlock code={step.code} label={step.codeLabel} />}
            </div>
          </li>
        ))}
      </ol>

      <p className="byo-foot">
        Full instructions and example datasets live in the{" "}
        <a href={REPO_URL} target="_blank" rel="noreferrer noopener">
          repository README
        </a>
        .
      </p>
    </section>
  );
});
