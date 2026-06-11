import { useEffect, useRef, useState } from "react";
import { fetchSchema } from "../useEvents";

interface SchemaViewerProps {
  dbId: string | null;
}

interface SchemaState {
  /** Which db_id the cached schema belongs to. */
  forDbId: string | null;
  open: boolean;
  schema: string | null;
  loading: boolean;
  error: string | null;
}

const INITIAL: SchemaState = {
  forDbId: null,
  open: false,
  schema: null,
  loading: false,
  error: null,
};

/**
 * Collapsible "View schema" affordance. Lazily fetches DDL via GET /schema the
 * first time it is opened for a given database, and re-fetches when the
 * database changes. Uses a native <details> element for accessible disclosure.
 *
 * State is consolidated so a database change resets everything in one update
 * derived during render (no synchronous setState-in-effect).
 */
export function SchemaViewer({ dbId }: SchemaViewerProps) {
  const [state, setState] = useState<SchemaState>(INITIAL);
  const reqId = useRef(0);

  // When the active database changes, reset cached schema during render.
  if (state.forDbId !== dbId) {
    setState({ ...INITIAL, forDbId: dbId });
  }

  const { open, schema, loading, error } = state;

  // Fetch once we are open, have a db, and have neither a result nor an error.
  // `loading` is set when opening; the fetch lives here so it stays cancellable.
  const shouldFetch = open && !!dbId && schema === null && error === null;

  useEffect(() => {
    if (!shouldFetch || !dbId) return;
    const myReq = ++reqId.current;
    fetchSchema(dbId)
      .then((ddl) => {
        if (myReq !== reqId.current) return;
        setState((s) => ({ ...s, schema: ddl, loading: false }));
      })
      .catch(() => {
        if (myReq !== reqId.current) return;
        setState((s) => ({
          ...s,
          error: "Could not load schema.",
          loading: false,
        }));
      });
  }, [shouldFetch, dbId]);

  // Opening starts the load synchronously (in the event handler, not an effect)
  // so the loading flag is set before the async fetch resolves.
  const setOpen = (next: boolean) =>
    setState((s) => ({
      ...s,
      open: next,
      loading: next && s.schema === null && !s.error ? true : s.loading,
    }));

  if (!dbId) return null;

  return (
    <details
      className="schema"
      open={open}
      onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}
    >
      <summary className="schema-summary">
        <span className="schema-summary-label">View schema</span>
        <span className="schema-chevron" aria-hidden="true">
          ▸
        </span>
      </summary>
      <div className="schema-body">
        {loading && <p className="schema-status">Loading DDL…</p>}
        {error && <p className="schema-status schema-error">{error}</p>}
        {schema !== null && !loading && (
          <pre className="schema-pre">
            <code>{schema}</code>
          </pre>
        )}
      </div>
    </details>
  );
}
