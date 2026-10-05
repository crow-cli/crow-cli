/**
 * The tab strip over the editor: one tab per open path, a dot when the server
 * holds unsaved work for it, and a close button that asks first.
 */
import { useState } from "react";
import { XIcon } from "lucide-react";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useWorkStore } from "@/lib/work-store";

const basename = (path: string) => path.split("/").pop() ?? path;

export function EditorTabs() {
  const tabs = useWorkStore((s) => s.tabs);
  const active = useWorkStore((s) => s.active);
  const activate = useWorkStore((s) => s.activate);
  const closeTab = useWorkStore((s) => s.closeTab);
  const save = useWorkStore((s) => s.save);
  // One joined string, so the strip re-renders when dirtiness changes and not
  // on every keystroke.
  const dirty = useWorkStore((s) =>
    s.tabs.filter((path) => s.buffers[path]?.dirty).join("\n"),
  );
  const [confirming, setConfirming] = useState<string | null>(null);
  const dirtyPaths = new Set(dirty.split("\n").filter(Boolean));

  if (!tabs.length) return null;

  const requestClose = (path: string) => {
    if (dirtyPaths.has(path)) setConfirming(path);
    else void closeTab(path);
  };

  return (
    <>
      <div
        role="tablist"
        aria-label="Open files"
        className="bg-muted/30 flex h-9 shrink-0 items-stretch overflow-x-auto border-b"
      >
        {tabs.map((path) => {
          const isActive = path === active;
          const isDirty = dirtyPaths.has(path);
          return (
            <div
              key={path}
              role="tab"
              aria-selected={isActive}
              data-testid="editor-tab"
              data-active={isActive}
              data-path={path}
              title={path}
              onClick={() => activate(path)}
              onMouseDown={(e) => {
                // middle click closes, the way every editor does it
                if (e.button === 1) {
                  e.preventDefault();
                  requestClose(path);
                }
              }}
              className={cn(
                "group flex max-w-56 min-w-0 cursor-pointer items-center gap-2 border-r px-3 text-xs select-none",
                isActive
                  ? "bg-background text-foreground"
                  : "text-muted-foreground hover:bg-accent/50 hover:text-foreground",
              )}
            >
              <span className="truncate">{basename(path)}</span>
              {isDirty && (
                <span
                  data-testid="dirty-dot"
                  title="unsaved"
                  className="bg-foreground/70 size-1.5 shrink-0 rounded-full"
                />
              )}
              <button
                type="button"
                aria-label={`Close ${basename(path)}`}
                data-testid="tab-close"
                onClick={(e) => {
                  e.stopPropagation();
                  requestClose(path);
                }}
                className={cn(
                  "-me-1 shrink-0 rounded-sm p-0.5 opacity-0 group-hover:opacity-100 focus-visible:opacity-100",
                  isActive && "opacity-60",
                  "hover:bg-muted hover:opacity-100",
                )}
              >
                <XIcon className="size-3" />
              </button>
            </div>
          );
        })}
      </div>

      <AlertDialog open={confirming !== null} onOpenChange={(open) => !open && setConfirming(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {confirming ? basename(confirming) : ""} has unsaved changes
            </AlertDialogTitle>
            <AlertDialogDescription>
              crow-web keeps the unsaved buffer even after the tab closes, so
              reopening the path brings it back. Saving writes it to disk first.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <Button
              variant="outline"
              data-testid="close-keep"
              onClick={() => {
                const path = confirming;
                setConfirming(null);
                if (path) void closeTab(path);
              }}
            >
              Close tab
            </Button>
            <AlertDialogAction
              data-testid="save-and-close"
              onClick={async () => {
                const path = confirming;
                setConfirming(null);
                if (!path) return;
                await save(path);
                await closeTab(path);
              }}
            >
              Save and close
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
