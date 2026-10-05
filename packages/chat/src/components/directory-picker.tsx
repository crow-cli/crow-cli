import { useEffect, useState } from "react";
import { ArrowUpIcon, FolderIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";
import { fsClient, type Entry, type Tree } from "@/lib/fs-client";

/** Absolute parent of an absolute path; `null` at the filesystem root. */
function parentOf(path: string): string | null {
  if (path === "/") return null;
  const trimmed = path.endsWith("/") ? path.slice(0, -1) : path;
  const idx = trimmed.lastIndexOf("/");
  if (idx <= 0) return "/";
  return trimmed.slice(0, idx);
}

/**
 * A real filesystem directory picker: browse anywhere on disk through the
 * `/fs` `browse` op (absolute paths, the served root untouched), then commit
 * the chosen directory as the new cwd. Replaces the free-text cwd input.
 */
export function DirectoryPicker({
  open,
  onOpenChange,
  initial,
  onSelect,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  initial: string;
  onSelect: (path: string) => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Working directory</DialogTitle>
          <DialogDescription>
            Pick the directory the agent and the work pane (editor, explorer,
            terminal) serve. Saving starts a new session in it.
          </DialogDescription>
        </DialogHeader>
        <PickerBody
          key={open ? initial : "closed"}
          initial={initial}
          onSelect={(path) => {
            onSelect(path);
            onOpenChange(false);
          }}
          onClose={() => onOpenChange(false)}
        />
      </DialogContent>
    </Dialog>
  );
}

function PickerBody({
  initial,
  onSelect,
  onClose,
}: {
  initial: string;
  onSelect: (path: string) => void;
  onClose: () => void;
}) {
  const [current, setCurrent] = useState(initial);
  const [entries, setEntries] = useState<Entry[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    setError(null);
    setEntries(null);
    fsClient
      .ready()
      .then(() => fsClient.call<Tree>("browse", { path: current }))
      .then((tree) => {
        if (live) setEntries(tree.entries);
      })
      .catch((e) => {
        if (live) setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      live = false;
    };
  }, [current]);

  const up = parentOf(current);
  const folders = entries?.filter((entry) => entry.type === "dir") ?? [];
  const files = entries?.filter((entry) => entry.type === "file") ?? [];

  return (
    <>
      <div className="flex items-center gap-2">
        <Button
          variant="outline"
          size="icon"
          disabled={!up}
          aria-label="Up one directory"
          title="Up one directory"
          onClick={() => up && setCurrent(up)}
        >
          <ArrowUpIcon className="size-4" />
        </Button>
        <span
          data-testid="picker-path"
          className="text-muted-foreground min-w-0 flex-1 truncate font-mono text-xs"
          title={current}
        >
          {current}
        </span>
      </div>
      <ScrollArea className="h-64 rounded-md border">
        {error ? (
          <div className="text-destructive p-4 text-xs">{error}</div>
        ) : entries === null ? (
          <div className="text-muted-foreground p-4 text-xs">Reading…</div>
        ) : entries.length === 0 ? (
          <div className="text-muted-foreground p-4 text-xs">
            Empty directory.
          </div>
        ) : (
          <div className="p-1">
            {folders.map((entry) => (
              <button
                key={entry.path}
                type="button"
                data-testid={`dir-${entry.name}`}
                className="hover:bg-accent flex w-full items-center gap-2 rounded px-2 py-1 text-left text-xs"
                onClick={() => setCurrent(entry.path)}
              >
                <FolderIcon className="text-muted-foreground size-4 shrink-0" />
                <span className="truncate">{entry.name}</span>
              </button>
            ))}
            {files.map((entry) => (
              <div
                key={entry.path}
                className="text-muted-foreground flex w-full items-center gap-2 rounded px-2 py-1 text-xs"
              >
                <span className="size-4 shrink-0" />
                <span className="truncate">{entry.name}</span>
              </div>
            ))}
          </div>
        )}
      </ScrollArea>
      <DialogFooter>
        <Button variant="ghost" onClick={onClose}>
          Cancel
        </Button>
        <Button onClick={() => onSelect(current)}>Use this directory</Button>
      </DialogFooter>
    </>
  );
}
