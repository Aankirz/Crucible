const REPO_URL = "https://github.com/Aankirz/Crucible";

interface SiteFooterProps {
  /** Scroll to the live console (re-uses the hero CTA target). */
  onLaunch: () => void;
}

/**
 * Footer with links to the hosted app, the repo, and the build credit.
 * The "hosted app" link scrolls to the console rather than guessing an
 * external URL that may differ per deploy.
 */
export function SiteFooter({ onLaunch }: SiteFooterProps) {
  return (
    <footer className="site-footer">
      <div className="footer-brand">
        <span className="flame flame-sm" aria-hidden="true" />
        <div>
          <strong>Crucible</strong>
          <span className="footer-tag">self-improving text-to-SQL</span>
        </div>
      </div>

      <nav className="footer-links" aria-label="Footer">
        <button type="button" className="footer-link" onClick={onLaunch}>
          Launch console
        </button>
        <a
          className="footer-link"
          href={REPO_URL}
          target="_blank"
          rel="noreferrer noopener"
        >
          GitHub repo ↗
        </a>
      </nav>

      <p className="footer-credit">
        Built with <span className="footer-accent">Gemini 3</span> +{" "}
        <span className="footer-accent">Arize Phoenix</span>
      </p>
    </footer>
  );
}
