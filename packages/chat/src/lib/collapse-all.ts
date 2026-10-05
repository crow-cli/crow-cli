import { useEffect, useSyncExternalStore } from "react";

let collapsed = false;
const listeners = new Set<() => void>();

const subscribe = (listener: () => void) => {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
};

/**
 * The `ctrl+o` twin: one flag collapses every tool card and thought to a
 * single line. Module-level on purpose — it is a view preference for the whole
 * tab, so it survives thread switches and scrolls; a reload starts expanded.
 */
export const collapseAll = {
  get: () => collapsed,
  set(next: boolean) {
    if (collapsed === next) return;
    collapsed = next;
    for (const listener of listeners) listener();
  },
  toggle: () => collapseAll.set(!collapsed),
};

export const useCollapseAll = () =>
  useSyncExternalStore(subscribe, collapseAll.get);

/** ctrl+o is the browser's "open file", so the chord gains a shift. */
export function useCollapseAllKey() {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.ctrlKey && e.shiftKey && (e.key === "O" || e.key === "o")) {
        e.preventDefault();
        collapseAll.toggle();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
}
