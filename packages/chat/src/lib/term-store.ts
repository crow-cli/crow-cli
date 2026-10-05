/**
 * The terminal tabs: which shells exist and which one is frontmost.
 *
 * Deliberately not persisted. A pty dies with the socket that owns it, so a
 * tab list that survived a reload would be a list of ghosts; the server's
 * `hello` pid is the only truth about what a tab is.
 */
import { create } from "zustand";

export type TermState = "live" | "exited" | "dropped";

export type TermTab = {
  id: number;
  label: string;
  state: TermState;
  /** The shell's pid as the server reported it; nothing until `hello`. */
  pid: number | null;
};

type TermStore = {
  tabs: TermTab[];
  active: number | null;
  add: () => number;
  close: (id: number) => void;
  activate: (id: number) => void;
  setState: (id: number, state: TermState, pid?: number | null) => void;
};

let seq = 0;

export const useTermStore = create<TermStore>()((set) => ({
  tabs: [],
  active: null,

  add: () => {
    seq += 1;
    const id = seq;
    set((state) => ({
      tabs: [...state.tabs, { id, label: `shell ${id}`, state: "live", pid: null }],
      active: id,
    }));
    return id;
  },

  close: (id) =>
    set((state) => {
      const tabs = state.tabs.filter((tab) => tab.id !== id);
      const index = state.tabs.findIndex((tab) => tab.id === id);
      return {
        tabs,
        active:
          state.active !== id
            ? state.active
            : (tabs[index]?.id ?? tabs[index - 1]?.id ?? tabs[0]?.id ?? null),
      };
    }),

  activate: (id) => set({ active: id }),

  setState: (id, termState, pid) =>
    set((state) => ({
      tabs: state.tabs.map((tab) =>
        tab.id === id ? { ...tab, state: termState, pid: pid ?? tab.pid } : tab,
      ),
    })),
}));
