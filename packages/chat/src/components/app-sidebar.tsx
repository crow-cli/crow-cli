import { memo, useEffect, useState } from "react";
import {
  Loader2Icon,
  PanelLeftCloseIcon,
  PanelLeftOpenIcon,
  PlusIcon,
  Trash2Icon,
} from "lucide-react";
import { useAcpAgentCapabilities } from "@assistant-ui/acp";
import {
  ThreadListItemPrimitive,
  ThreadListPrimitive,
  useAuiState,
} from "@assistant-ui/react";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Button, buttonVariants } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { useSidebarSetting } from "@/lib/settings";
import { cn } from "@/lib/utils";
import { relativeTime } from "@/lib/time";

/**
 * A load that settles in a frame or two never shows its placeholder. Saving a
 * new working directory remounts the runtime and re-asks `session/list`, and
 * four grey bars flashing over an empty rail for the length of that round trip
 * reads as the list breaking rather than as progress.
 */
function useDelayed(flag: boolean, ms: number) {
  const [shown, setShown] = useState(false);
  useEffect(() => {
    if (!flag) {
      setShown(false);
      return;
    }
    const timeoutId = setTimeout(() => setShown(true), ms);
    return () => clearTimeout(timeoutId);
  }, [flag, ms]);
  return shown;
}

/**
 * The threads crow-cli remembers for the current cwd, newest first — the
 * agent's own ordering, straight off `session/list`. Rows come from the
 * runtime's thread list, so switching, minting and deleting go through the
 * same adapter the package wires to `session/load` / `session/delete`.
 *
 * Memoized, because the host that owns the runtime re-renders on every
 * streamed chunk while this list only moves when a session is minted, switched
 * or deleted: without it, every row's delete dialog and icon re-render fifty
 * times a second for nothing. Its own store subscriptions still update it.
 */
export const AppSidebar = memo(function AppSidebar() {
  const isLoading = useAuiState((s) => s.threads.isLoading);
  const count = useAuiState((s) => s.threads.threadIds.length);
  const [collapsed, setCollapsed] = useSidebarSetting();
  const showSkeleton = useDelayed(isLoading && count === 0, 400);
  // `session/delete` is optional and advertised by presence, so an agent that
  // never implemented it has no trash to offer: the button would only produce
  // an error after the confirmation dialog.
  const canDelete =
    useAcpAgentCapabilities()?.sessionCapabilities?.delete != null;

  if (collapsed) {
    return (
      <div
        data-testid="thread-sidebar"
        data-state="collapsed"
        className="bg-sidebar text-sidebar-foreground flex w-10 shrink-0 flex-col items-center border-r py-2"
      >
        <Button
          data-testid="sidebar-toggle"
          variant="ghost"
          size="icon"
          aria-label="Show threads"
          title="Show threads"
          className="size-8"
          onClick={() => setCollapsed(false)}
        >
          <PanelLeftOpenIcon className="size-4" />
        </Button>
      </div>
    );
  }

  return (
    <aside
      data-testid="thread-sidebar"
      data-state="expanded"
      className="bg-sidebar text-sidebar-foreground flex w-64 shrink-0 flex-col border-r"
    >
      <div className="flex h-12 shrink-0 items-center justify-between gap-2 border-b px-3">
        <span className="text-sm font-medium">Threads</span>
        <div className="flex items-center gap-0.5">
          <ThreadListPrimitive.New asChild>
            <Button
              data-testid="new-thread"
              variant="ghost"
              size="sm"
              className="h-7 gap-1.5 px-2 text-xs"
            >
              <PlusIcon className="size-3.5" />
              New
            </Button>
          </ThreadListPrimitive.New>
          <Button
            data-testid="sidebar-toggle"
            variant="ghost"
            size="icon"
            aria-label="Hide threads"
            title="Hide threads"
            className="size-7"
            onClick={() => setCollapsed(true)}
          >
            <PanelLeftCloseIcon className="size-3.5" />
          </Button>
        </div>
      </div>
      <ScrollArea className="min-h-0 flex-1">
        {/* A refresh (every turn start/end re-asks session/list) must not
            flash placeholders over rows we already have. */}
        {showSkeleton && <ThreadListSkeleton />}
        <ThreadListPrimitive.Root
          data-testid="thread-list"
          className="flex flex-col gap-0.5 p-2"
        >
          <ThreadListPrimitive.Items>
            {() => <ThreadRow canDelete={canDelete} />}
          </ThreadListPrimitive.Items>
        </ThreadListPrimitive.Root>
        {!isLoading && count === 0 && (
          <p
            data-testid="thread-list-empty"
            className="text-muted-foreground px-3 py-6 text-xs"
          >
            No threads for this directory yet. Send a message to start one.
          </p>
        )}
      </ScrollArea>
    </aside>
  );
});

function ThreadListSkeleton() {
  return (
    <div
      role="status"
      aria-label="Loading threads"
      className="flex flex-col gap-1 p-2"
    >
      {Array.from({ length: 4 }, (_, i) => (
        <Skeleton key={i} className="h-9 w-full" />
      ))}
    </div>
  );
}

function ThreadRow({ canDelete }: { canDelete: boolean }) {
  const id = useAuiState((s) => s.threadListItem.id);
  const title = useAuiState((s) => s.threadListItem.title);
  const isRunning = useAuiState((s) => s.threadListItem.isRunning);
  const updatedAt = useAuiState((s) => {
    const value = s.threadListItem.custom?.updatedAt;
    return typeof value === "string" ? value : undefined;
  });
  const when = relativeTime(updatedAt);

  return (
    <ThreadListItemPrimitive.Root
      data-testid="thread-item"
      data-thread-id={id}
      className="group hover:bg-muted data-active:bg-muted relative flex rounded-md transition-colors"
    >
      <ThreadListItemPrimitive.Trigger
        data-testid="thread-open"
        className="focus-visible:ring-ring/50 flex min-w-0 flex-1 flex-col items-start gap-0.5 rounded-md py-1.5 pe-2.5 ps-2.5 text-start focus-visible:ring-1 focus-visible:outline-none"
      >
        <span className="flex w-full min-w-0 items-center gap-1.5">
          {isRunning && (
            <Loader2Icon
              aria-hidden
              className="text-muted-foreground size-3 shrink-0 animate-spin"
            />
          )}
          <span className="min-w-0 flex-1 truncate text-xs">
            <ThreadListItemPrimitive.Title fallback={id} />
          </span>
        </span>
        {when && (
          <span
            data-testid="thread-updated"
            className="text-muted-foreground w-full truncate text-[11px]"
          >
            {when}
          </span>
        )}
      </ThreadListItemPrimitive.Trigger>
      {canDelete && <ThreadDelete title={title || id} />}
    </ThreadListItemPrimitive.Root>
  );
}

/** Deleting is destructive on the agent, so it is always confirmed. */
function ThreadDelete({ title }: { title: string }) {
  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button
          data-testid="thread-delete"
          variant="ghost"
          size="icon"
          aria-label="Delete thread"
          className="absolute end-1 top-1/2 size-6 -translate-y-1/2 p-0 opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 group-data-active:opacity-100"
        >
          <Trash2Icon className="size-3.5" />
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Delete this thread?</AlertDialogTitle>
          <AlertDialogDescription>
            The agent forgets{" "}
            <span className="text-foreground font-medium">{title}</span>. This
            cannot be undone.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction asChild>
            <ThreadListItemPrimitive.Delete
              data-testid="thread-delete-confirm"
              className={cn(buttonVariants({ variant: "destructive" }))}
            >
              Delete
            </ThreadListItemPrimitive.Delete>
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
