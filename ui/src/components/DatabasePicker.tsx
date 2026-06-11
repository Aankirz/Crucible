import type { DatabaseInfo } from "../useEvents";

interface DatabasePickerProps {
  databases: DatabaseInfo[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  loading: boolean;
  error: string | null;
}

/**
 * Database dropdown populated from GET /databases. Shows the selected db's
 * domain and a demo/live mode badge. Disabled while loading or on error.
 */
export function DatabasePicker({
  databases,
  selectedId,
  onSelect,
  loading,
  error,
}: DatabasePickerProps) {
  const selected = databases.find((d) => d.id === selectedId) ?? null;

  return (
    <div className="db-picker">
      <label className="field-label" htmlFor="db-select">
        Database
      </label>

      <div className="db-picker-row">
        <div className="select-wrap">
          <select
            id="db-select"
            className="db-select"
            value={selectedId ?? ""}
            onChange={(e) => onSelect(e.target.value)}
            disabled={loading || databases.length === 0}
          >
            {loading && <option value="">Loading databases…</option>}
            {!loading && databases.length === 0 && (
              <option value="">No databases available</option>
            )}
            {databases.map((db) => (
              <option key={db.id} value={db.id}>
                {db.name}
              </option>
            ))}
          </select>
          <span className="select-caret" aria-hidden="true">
            ▾
          </span>
        </div>

        {selected && (
          <span
            className={`mode-badge mode-${selected.mode}`}
            title={
              selected.mode === "demo"
                ? "Deterministic instant demo"
                : "Real Gemini 3 run"
            }
          >
            {selected.mode}
          </span>
        )}
      </div>

      {error && <p className="db-error">{error}</p>}

      {selected && (
        <p className="db-meta">
          <span className="db-domain">{selected.domain}</span>
          <span className="db-dot" aria-hidden="true">
            ·
          </span>
          <span>{selected.num_questions} gold questions</span>
          <span className="db-dot" aria-hidden="true">
            ·
          </span>
          <span>{selected.tables.length} tables</span>
        </p>
      )}

      {selected?.blurb && <p className="db-blurb">{selected.blurb}</p>}
    </div>
  );
}
