/**
 * The work pane: everything crow-web owns a view of — the editor today, the
 * explorer and the terminals as they land.
 */
import { useCallback, useEffect, useState } from "react";
import {
  FilePlusIcon,
  PanelBottomCloseIcon,
  PanelBottomOpenIcon,
  PanelLeftIcon,
  PanelLeftOpenIcon,
  PanelRightCloseIcon,
} from "lucide-react";
import type { PanelImperativeHandle } from "react-resizable-panels";
import { CodeEditor, languageOfPath } from "@crow/editor";
import { Explorer } from "@/components/explorer/explorer";
import { TerminalPane } from "@/components/terminal/terminal-pane";
import { EditorTabs } from "@/components/work/editor-tabs";
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/components/ui/resizable";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { cn } from "@/lib/utils";
import { useColorScheme } from "@/lib/theme";
import {
  DEFAULT_INNER,
  DEFAULT_VERT,
  bootWorkStore,
  useWorkStore,
} from "@/lib/work-store";

const DOT: Record<string, string> = {
  open: "bg-success",
  connecting: "bg-warning animate-pulse",
  closed: "bg-destructive",
};

const basename = (path: string) => path.split("/").pop() ?? path;

export function WorkPane() {
  const active = useWorkStore((s) => s.active);
  const buffer = useWorkStore((s) => (s.active ? s.buffers[s.active] : undefined));
  const status = useWorkStore((s) => s.status);
  const root = useWorkStore((s) => s.root);
  const error = useWorkStore((s) => s.error);
  const edit = useWorkStore((s) => s.edit);
  const save = useWorkStore((s) => s.save);
  const togglePane = useWorkStore((s) => s.togglePane);
  const dismissError = useWorkStore((s) => s.dismissError);
  const inner = useWorkStore((s) => s.inner);
  const setInner = useWorkStore((s) => s.setInner);
  const attachExplorerPanel = useWorkStore((s) => s.attachExplorerPanel);
  const explorerHidden = useWorkStore((s) => s.explorerCollapsed);
  const toggleExplorer = useWorkStore((s) => s.toggleExplorer);
  const vert = useWorkStore((s) => s.vert);
  const setVert = useWorkStore((s) => s.setVert);
  const attachTermPanel = useWorkStore((s) => s.attachTermPanel);
  const termHidden = useWorkStore((s) => s.termCollapsed);
  const toggleTerm = useWorkStore((s) => s.toggleTerm);
  const scheme = useColorScheme();

  const explorerRef = useCallback(
    (handle: PanelImperativeHandle | null) => attachExplorerPanel(handle),
    [attachExplorerPanel],
  );

  const termRef = useCallback(
    (handle: PanelImperativeHandle | null) => attachTermPanel(handle),
    [attachTermPanel],
  );

  useEffect(() => bootWorkStore(), []);

  // Ctrl+S saves whatever tab is frontmost, including when focus is on the tab
  // strip rather than in CodeMirror (which has its own binding, and marks the
  // event handled).
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (!(event.metaKey || event.ctrlKey) || event.key.toLowerCase() !== "s") return;
      // CodeMirror's own Mod-s binding runs first and marks the event handled;
      // this is the fallback for focus anywhere else in the window.
      if (event.defaultPrevented) return;
      event.preventDefault();
      if (active) void save(active);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [active, save]);

  return (
    <div className="bg-background flex h-full min-w-0 flex-col">
      <header className="text-muted-foreground flex h-9 shrink-0 items-center gap-2 border-b px-3 text-xs">
        <span
          data-testid="work-status"
          data-state={status}
          title={`crow-web: ${status}`}
          className={cn("size-1.5 shrink-0 rounded-full", DOT[status])}
        />
        <span data-testid="work-root" className="truncate font-medium" title={root}>
          {root ? basename(root) : "crow-web"}
        </span>
        <span className="flex-1" />
        <Button
          variant="ghost"
          size="icon"
          className="size-6"
          data-testid="term-toggle"
          data-state={termHidden ? "hidden" : "shown"}
          aria-label={termHidden ? "Show the terminal" : "Hide the terminal"}
          title="Toggle the terminal"
          onClick={toggleTerm}
        >
          {termHidden ? (
            <PanelBottomOpenIcon className="size-4" />
          ) : (
            <PanelBottomCloseIcon className="size-4" />
          )}
        </Button>
        <Button
          variant="ghost"
          size="icon"
          className="size-6"
          data-testid="explorer-toggle"
          data-state={explorerHidden ? "hidden" : "shown"}
          aria-label={explorerHidden ? "Show the explorer" : "Hide the explorer"}
          title="Toggle the explorer"
          onClick={toggleExplorer}
        >
          {explorerHidden ? (
            <PanelLeftOpenIcon className="size-4" />
          ) : (
            <PanelLeftIcon className="size-4" />
          )}
        </Button>
        <OpenPath />
        <Button
          variant="ghost"
          size="icon"
          aria-label="Hide the work pane"
          data-testid="work-hide"
          className="size-6"
          onClick={togglePane}
        >
          <PanelRightCloseIcon className="size-4" />
        </Button>
      </header>

      <div className="min-h-0 flex-1">
        <ResizablePanelGroup
          id="work-vert"
          orientation="vertical"
          defaultLayout={vert ?? DEFAULT_VERT}
          onLayoutChanged={(next, meta) => setVert(meta.requestedLayout ?? next)}
        >
          <ResizablePanel id="top" minSize="35" className="min-h-0">
            <ResizablePanelGroup
              id="work-inner"
              orientation="horizontal"
              defaultLayout={inner ?? DEFAULT_INNER}
              onLayoutChanged={(next, meta) => setInner(meta.requestedLayout ?? next)}
            >
              <ResizablePanel
                id="explorer"
                collapsible
                collapsedSize={0}
                minSize="22"
                maxSize="60"
                panelRef={explorerRef}
                className="min-w-0"
              >
                <Explorer />
              </ResizablePanel>
              <ResizableHandle />
              <ResizablePanel id="editor" minSize="30" className="min-w-0">
                <div className="flex h-full min-h-0 flex-col">
                  <EditorTabs />
                  <div className="relative min-h-0 flex-1">
                    {active && buffer ? (
                      <CodeEditor
                        key={active}
                        language={languageOfPath(active)}
                        value={buffer.content}
                        rev={buffer.rev}
                        scheme={scheme}
                        onChange={(content) => edit(active, content)}
                        onSave={() => void save(active)}
                      />
                    ) : (
                      <Empty />
                    )}
                  </div>
                </div>
              </ResizablePanel>
            </ResizablePanelGroup>
          </ResizablePanel>
          <ResizableHandle />
          <ResizablePanel
            id="term"
            collapsible
            collapsedSize={0}
            minSize="15"
            maxSize="70"
            panelRef={termRef}
            className="min-h-0"
          >
            <TerminalPane />
          </ResizablePanel>
        </ResizablePanelGroup>
      </div>

      {error && (
        <div
          data-testid="work-error"
          className="bg-destructive/10 text-destructive flex shrink-0 items-center gap-2 border-t px-3 py-1.5 text-xs"
        >
          <span className="flex-1 truncate">{error}</span>
          <button type="button" aria-label="Dismiss" onClick={dismissError}>
            ✕
          </button>
        </div>
      )}
    </div>
  );
}

/**
 * Jump-to-path. The explorer is the real door (Phase 4); this stays as the
 * way to open something you already know the name of.
 */
function OpenPath() {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const openPath = useWorkStore((s) => s.open);
  return (
    <Popover
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) setDraft("");
      }}
    >
      <PopoverTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className="size-6"
          aria-label="Open a path"
          data-testid="open-path"
        >
          <FilePlusIcon className="size-4" />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-80">
        <form
          className="flex flex-col gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            const path = draft.trim();
            if (!path) return;
            void openPath(path);
            setOpen(false);
          }}
        >
          <label htmlFor="work-path" className="text-xs font-medium">
            Open a path
          </label>
          <p className="text-muted-foreground text-xs">
            Relative to the served root.
          </p>
          <Input
            id="work-path"
            data-testid="open-path-input"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="src/App.tsx"
            className="font-mono text-xs"
          />
          <Button type="submit" size="sm" className="self-end">
            Open
          </Button>
        </form>
      </PopoverContent>
    </Popover>
  );
}

function Empty() {
  return (
    <div className="text-muted-foreground flex h-full flex-col items-center justify-center gap-1 text-xs">
      <span>No file open.</span>
      <span>Pick a file in the explorer, or open a path above.</span>
    </div>
  );
}
