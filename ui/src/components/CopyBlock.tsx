import { useState } from "react";

interface CopyBlockProps {
  /** The code/command to display and copy. */
  code: string;
  /** Optional short label rendered above the block (e.g. "clone"). */
  label?: string;
}

/**
 * A monospace code block with a copy-to-clipboard affordance. Used in the
 * "bring your own database" guide. Falls back gracefully when the Clipboard
 * API is unavailable (older Safari / insecure contexts).
 */
export function CopyBlock({ code, label }: CopyBlockProps) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      // Clipboard unavailable — the code is still selectable by the user.
    }
  };

  return (
    <div className="copy-block">
      {label && <span className="copy-label">{label}</span>}
      <pre className="copy-pre">
        <code>{code}</code>
      </pre>
      <button
        type="button"
        className="copy-btn"
        onClick={() => void copy()}
        aria-label={copied ? "Copied to clipboard" : "Copy to clipboard"}
      >
        {copied ? "Copied ✓" : "Copy"}
      </button>
    </div>
  );
}
