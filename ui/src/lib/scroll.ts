/** Imperative DOM helpers for scroll/focus orchestration on the single page. */

/** Focus the database <select> inside the given console section, if present. */
export function focusSelect(el: HTMLElement | null): void {
  el?.querySelector<HTMLSelectElement>("#db-select")?.focus();
}
