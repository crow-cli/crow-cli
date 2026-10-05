/**
 * The bottom of the work pane: a strip of shells and their terminals.
 *
 * Every tab keeps its own TerminalView mounted (hidden, not unmounted) so
 * scrollback and the running shell survive a tab switch; the strip is the
 * only chrome, and "+" is the only way a shell is born.
 */
import { PlusIcon, SquareTerminalIcon, XIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { TerminalView } from "@/components/terminal/terminal-view";
import { cn } from "@/lib/utils";
import { useTermStore } from "@/lib/term-store";

export function TerminalPane() {
  const tabs = useTermStore((s) => s.tabs);
  const active = useTermStore((s) => s.active);
  const add = useTermStore((s) => s.add);
  const close = useTermStore((s) => s.close);
  const activate = useTermStore((s) => s.activate);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div
        role="tablist"
        aria-label="Terminals"
        data-testid="term-tabs"
        className="bg-muted/30 flex h-8 shrink-0 items-stretch overflow-x-auto border-b"
      >
        {tabs.map((tab) => {
          const isActive = tab.id === active;
          return (
            <div
              key={tab.id}
              role="tab"
              aria-selected={isActive}
              data-testid="term-tab"
              data-id={tab.id}
              data-state={tab.state}
              title={tab.pid ? `${tab.label} (pid ${tab.pid})` : tab.label}
              onClick={() => activate(tab.id)}
              className={cn(
                "group flex max-w-56 min-w-0 cursor-pointer items-center gap-2 border-r px-3 text-xs select-none",
                isActive
                  ? "bg-background text-foreground"
                  : "text-muted-foreground hover:bg-accent/50 hover:text-foreground",
              )}
            >
              <SquareTerminalIcon className="size-3.5 shrink-0" />
              <span className="truncate">{tab.label}</span>
              {tab.state !== "live" && (
                <span className="text-muted-foreground shrink-0" data-testid="term-dead">
                  {tab.state}
                </span>
              )}
              <button
                type="button"
                aria-label={`Close ${tab.label}`}
                data-testid="term-close"
                data-id={tab.id}
                onClick={(event) => {
                  event.stopPropagation();
                  close(tab.id);
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
        <Button
          variant="ghost"
          size="icon"
          className="size-6 shrink-0 self-center"
          data-testid="term-add"
          aria-label="New terminal"
          title="New terminal"
          onClick={() => add()}
        >
          <PlusIcon className="size-4" />
        </Button>
      </div>
      <div className="relative min-h-0 flex-1">
        {tabs.map((tab) => (
          <TerminalView key={tab.id} id={tab.id} active={tab.id === active} />
        ))}
        {tabs.length === 0 && (
          <div className="text-muted-foreground flex h-full flex-col items-center justify-center gap-2 text-xs">
            <span>No shell running.</span>
            <Button variant="outline" size="sm" data-testid="term-add-empty" onClick={() => add()}>
              <PlusIcon className="size-3.5" />
              Start a terminal
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
