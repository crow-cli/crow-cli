/**
 * The work pane's state: which paths are open, what the server says their
 * buffers hold, and how the pane is sized.
 *
 * The server is authoritative. Typing writes through to crow-web (debounced,
 * because a keystroke is not a save), and every buffer that comes back is
 * compared against what we already hold: same content means it is the echo of
 * our own write, different content means another tab moved it and the editor
 * has to be told — that is what `rev` is for.
 */
import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { PanelImperativeHandle } from "react-resizable-panels";
import {
  fsClient,
  type CloseReply,
  type ConnectionState,
  type FileView,
} from "@/lib/fs-client";

export type Layout = Record<string, number>;

export const DEFAULT_LAYOUT: Layout = { chat: 62, work: 38 };

export const DEFAULT_INNER: Layout = { explorer: 34, editor: 66 };

export const DEFAULT_VERT: Layout = { top: 68, term: 32 };

/** A server FileView plus the revision the editor keys its re-reads on. */
export type Buffer = FileView & { rev: number };

type WorkState = {
  status: ConnectionState;
  root: string;
  /** Open paths, left to right. */
  tabs: string[];
  active: string | null;
  buffers: Record<string, Buffer>;
  error: string | null;
  /** Bumped on every tree-moving event; the explorer re-reads on it. */
  treeRev: number;
  layout: Layout | null;
  collapsed: boolean;
  panel: PanelImperativeHandle | null;
  /** The work pane's own split: explorer column vs editor. */
  inner: Layout | null;
  explorerCollapsed: boolean;
  explorerPanel: PanelImperativeHandle | null;
  /** Editor block vs terminal block. */
  vert: Layout | null;
  termCollapsed: boolean;
  termPanel: PanelImperativeHandle | null;

  open: (path: string, opts?: { dropIfMissing?: boolean }) => Promise<void>;
  /** Re-root the served tree to `path`; the server's hello does the reset. */
  reroot: (path: string) => Promise<void>;
  activate: (path: string | null) => void;
  edit: (path: string, content: string) => void;
  save: (path: string) => Promise<void>;
  closeTab: (path: string) => Promise<void>;
  attachPanel: (panel: PanelImperativeHandle | null) => void;
  setLayout: (layout: Layout) => void;
  togglePane: () => void;
  attachExplorerPanel: (panel: PanelImperativeHandle | null) => void;
  setInner: (layout: Layout) => void;
  toggleExplorer: () => void;
  attachTermPanel: (panel: PanelImperativeHandle | null) => void;
  setVert: (layout: Layout) => void;
  toggleTerm: () => void;
  dismissError: () => void;
  fail: (error: unknown) => void;
};

/** Writes waiting on their debounce, per path. */
const queued = new Map<string, { content: string; timer: ReturnType<typeof setTimeout> }>();
const WRITE_DEBOUNCE = 120;

function flush(path: string) {
  const pending = queued.get(path);
  if (!pending) return;
  clearTimeout(pending.timer);
  queued.delete(path);
  fsClient
    .call<FileView>("write", { path, text: pending.content })
    .catch((error) => useWorkStore.getState().fail(error));
}

let booted = false;

export const useWorkStore = create<WorkState>()(
  persist(
    (set, get) => ({
      status: "closed",
      root: "",
      tabs: [],
      active: null,
      buffers: {},
      error: null,
      treeRev: 0,
      layout: null,
      collapsed: false,
      panel: null,
      inner: null,
      explorerCollapsed: false,
      explorerPanel: null,
      vert: null,
      termCollapsed: false,
      termPanel: null,

      fail: (error: unknown) =>
        set({ error: error instanceof Error ? error.message : String(error) }),

      reroot: async (path) => {
        await fsClient.ready();
        try {
          await fsClient.call("reroot", { path });
        } catch (error) {
          get().fail(error);
        }
      },

      open: async (path, opts) => {
        try {
          const view = await fsClient.call<FileView>("read", { path });
          set((state) => {
            const held = state.buffers[view.path];
            return {
              tabs: state.tabs.includes(view.path)
                ? state.tabs
                : [...state.tabs, view.path],
              active: view.path,
              error: null,
              buffers: {
                ...state.buffers,
                [view.path]: {
                  ...view,
                  rev: held && held.content === view.content ? held.rev : (held?.rev ?? 0) + 1,
                },
              },
            };
          });
        } catch (error) {
          // A tab that outlived its file (the list is in localStorage, the file
          // is not) should quietly disappear on the next boot, not shout.
          if (opts?.dropIfMissing && /no such file/i.test(String((error as Error).message))) {
            set((state) => {
              const tabs = state.tabs.filter((tab) => tab !== path);
              const index = state.tabs.indexOf(path);
              return {
                tabs,
                active:
                  state.active !== path
                    ? state.active
                    : (tabs[index] ?? tabs[index - 1] ?? tabs[0] ?? null),
              };
            });
            return;
          }
          get().fail(error);
        }
      },

      activate: (path) => set({ active: path }),

      edit: (path, content) => {
        set((state) => {
          const held = state.buffers[path];
          return {
            buffers: {
              ...state.buffers,
              [path]: {
                path,
                mtime: held?.mtime ?? null,
                rev: held?.rev ?? 0,
                content,
                dirty: true,
              },
            },
          };
        });
        const pending = queued.get(path);
        if (pending) clearTimeout(pending.timer);
        queued.set(path, {
          content,
          timer: setTimeout(() => flush(path), WRITE_DEBOUNCE),
        });
      },

      save: async (path) => {
        // One socket, and the server answers a client's requests in order, so
        // flushing the queued write and then committing needs no await between.
        flush(path);
        try {
          const view = await fsClient.call<FileView>("commit", { path });
          set((state) => ({
            error: null,
            buffers: { ...state.buffers, [view.path]: adopt(state.buffers[view.path], view) },
          }));
        } catch (error) {
          get().fail(error);
        }
      },

      closeTab: async (path) => {
        flush(path);
        try {
          await fsClient.call<CloseReply>("close", { path });
        } catch (error) {
          get().fail(error);
        }
        // Kept or dropped, this tab is gone: a dirty buffer outlives us on the
        // server and comes back on the next open.
        set((state) => {
          const tabs = state.tabs.filter((tab) => tab !== path);
          const index = state.tabs.indexOf(path);
          const active =
            state.active !== path
              ? state.active
              : (tabs[index] ?? tabs[index - 1] ?? tabs[0] ?? null);
          const buffers = { ...state.buffers };
          delete buffers[path];
          return { tabs, active, buffers };
        });
      },

      attachPanel: (panel) => set({ panel }),

      setLayout: (layout) =>
        set({ layout, collapsed: (layout.work ?? 0) === 0 }),

      togglePane: () => {
        const panel = get().panel;
        if (!panel) return;
        if (panel.isCollapsed()) panel.expand();
        else panel.collapse();
      },

      attachExplorerPanel: (explorerPanel) => set({ explorerPanel }),

      setInner: (inner) =>
        set({ inner, explorerCollapsed: (inner.explorer ?? 0) === 0 }),

      toggleExplorer: () => {
        const panel = get().explorerPanel;
        if (!panel) return;
        if (panel.isCollapsed()) panel.expand();
        else panel.collapse();
      },

      attachTermPanel: (termPanel) => set({ termPanel }),

      setVert: (vert) => set({ vert, termCollapsed: (vert.term ?? 0) === 0 }),

      toggleTerm: () => {
        const panel = get().termPanel;
        if (!panel) return;
        if (panel.isCollapsed()) panel.expand();
        else panel.collapse();
      },

      dismissError: () => set({ error: null }),
    }),
    {
      name: "crow-chat.work",
      // Tabs and geometry survive a reload; buffer content does not, because
      // the server is where it lives.
      partialize: (state) => ({
        tabs: state.tabs,
        active: state.active,
        layout: state.layout,
        collapsed: state.collapsed,
        inner: state.inner,
        explorerCollapsed: state.explorerCollapsed,
        vert: state.vert,
        termCollapsed: state.termCollapsed,
      }),
    },
  ),
);

/** Same content is our own echo; different content came from elsewhere. */
function adopt(held: Buffer | undefined, view: FileView): Buffer {
  if (!held) return { ...view, rev: 1 };
  return {
    ...view,
    rev: held.content === view.content ? held.rev : held.rev + 1,
  };
}

/**
 * Wire the socket to the store. Called once from the work pane's mount
 * effect; the guard keeps HMR and StrictMode from doubling it up.
 */
export function bootWorkStore() {
  if (booted) return;
  booted = true;

  fsClient.onState((status) => useWorkStore.setState({ status }));
  fsClient.onEvent((event) => {
    const state = useWorkStore.getState();
    if (event.event === "hello") {
      const { root, buffers } = event.data;
      // A re-root is a new workspace: the server already dropped the old
      // buffers, so drop the old tabs and let the explorer re-read. The first
      // hello (root was still "") is a boot/reconnect, not a re-root.
      if (state.root && state.root !== root) {
        useWorkStore.setState({
          root,
          tabs: [],
          active: null,
          buffers: {},
          treeRev: state.treeRev + 1,
        });
        return;
      }
      const held: Record<string, Buffer> = {};
      const restored: string[] = [];
      for (const view of buffers) {
        held[view.path] = adopt(state.buffers[view.path], view);
        // Unsaved work the server kept for us — a reload should land on it
        // even if localStorage lost the tab list.
        if (view.dirty && !state.tabs.includes(view.path)) restored.push(view.path);
      }
      useWorkStore.setState({ root, buffers: { ...state.buffers, ...held } });
      const missing = [...state.tabs.filter((tab) => !held[tab]), ...restored];
      if (restored.length) {
        useWorkStore.setState((s) => ({ tabs: [...s.tabs, ...restored] }));
      }
      for (const path of missing) void state.open(path, { dropIfMissing: true });
      return;
    }
    if (event.event === "buffer") {
      const view = event.data;
      if (!state.tabs.includes(view.path)) return;
      useWorkStore.setState((s) => ({
        buffers: { ...s.buffers, [view.path]: adopt(s.buffers[view.path], view) },
      }));
      return;
    }
    const { kind, path, to } = event.data;
    useWorkStore.setState((s) => ({ treeRev: s.treeRev + 1 }));
    if (kind === "rename" && to && state.tabs.includes(path)) {
      const held = state.buffers[path];
      useWorkStore.setState((s) => {
        const buffers = { ...s.buffers };
        delete buffers[path];
        if (held) buffers[to] = { ...held, path: to, rev: held.rev + 1 };
        return {
          buffers,
          tabs: s.tabs.map((tab) => (tab === path ? to : tab)),
          active: s.active === path ? to : s.active,
        };
      });
    }
    if (kind === "delete" && state.tabs.includes(path)) {
      useWorkStore.setState((s) => {
        const buffers = { ...s.buffers };
        delete buffers[path];
        const tabs = s.tabs.filter((tab) => tab !== path);
        return { buffers, tabs, active: s.active === path ? (tabs[0] ?? null) : s.active };
      });
    }
  });

  fsClient.connect();
}
