import { useEffect, useMemo, useState, type KeyboardEvent } from "react";
import { useAcpAvailableCommands } from "@assistant-ui/acp";
import { useAui, useAuiState } from "@assistant-ui/react";
import { cn } from "@/lib/utils";

export type SlashMenuState = {
  open: boolean;
  query: string;
  total: number;
  filtered: readonly { name: string; description?: string | null }[];
  index: number;
  onIndex: (i: number) => void;
  onPick: (name: string) => void;
  onKeyDown: (e: KeyboardEvent) => void;
};

/**
 * The TUI's slash menu, minus the parts a browser cannot source honestly: it
 * lists exactly the commands the agent advertises in
 * `available_commands_update` (crow-cli sends four), not the TUI's own local
 * catalog and skills, so the grouping header says `commands` and nothing else.
 * Open state is derived from the composer text (`/^\/\S*$/`) so typing,
 * deleting and programmatic sets all agree; Esc remembers the text it closed
 * at and reopens as soon as the text moves.
 */
export function useSlashMenu(): SlashMenuState {
  const commands = useAcpAvailableCommands();
  const text = useAuiState((s) => s.composer.text);
  const aui = useAui();
  const [index, setIndex] = useState(0);
  const [escAt, setEscAt] = useState<string | null>(null);

  const query = /^\/(\S*)$/.exec(text)?.[1];
  const open =
    query !== undefined &&
    text !== escAt &&
    (commands?.length ?? 0) > 0;

  const filtered = useMemo(
    () =>
      (commands ?? [])
        .filter((c) => c.name.toLowerCase().startsWith(query?.toLowerCase() ?? ""))
        .map((c) => ({ name: c.name, description: c.description ?? null })),
    [commands, query],
  );

  useEffect(() => {
    setIndex(0);
  }, [query]);
  useEffect(() => {
    setIndex((i) => Math.min(i, Math.max(0, filtered.length - 1)));
  }, [filtered.length]);

  const refocus = () => {
    // picking with the mouse leaves focus on the button; the next Enter must
    // still reach the composer.
    requestAnimationFrame(() =>
      document
        .querySelector<HTMLTextAreaElement>("textarea.aui-composer-input")
        ?.focus(),
    );
  };

  const onPick = (name: string) => {
    aui.thread.composer().setText(`/${name} `);
    setEscAt(null);
    refocus();
  };

  const onKeyDown = (e: KeyboardEvent) => {
    if (!open || filtered.length === 0) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setIndex((i) => (i + 1) % filtered.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setIndex((i) => (i - 1 + filtered.length) % filtered.length);
    } else if (e.key === "Enter") {
      e.preventDefault();
      onPick(filtered[index].name);
    } else if (e.key === "Tab") {
      e.preventDefault();
      aui.thread.composer().setText(`/${filtered[index].name}`);
      setEscAt(null);
    } else if (e.key === "Escape") {
      e.preventDefault();
      setEscAt(text);
    }
  };

  return {
    open,
    query: query ?? "",
    total: commands?.length ?? 0,
    filtered,
    index,
    onIndex: setIndex,
    onPick,
    onKeyDown,
  };
}

export function SlashMenuPopup({ slash }: { slash: SlashMenuState }) {
  if (!slash.open) return null;
  return (
    <div
      data-testid="slash-menu"
      className="bg-popover text-popover-foreground absolute inset-x-0 bottom-full z-20 mb-2 overflow-hidden rounded-md border shadow-md"
    >
      <div className="text-muted-foreground flex items-center justify-between border-b px-2.5 py-1 text-[11px]">
        <span>commands</span>
        <span data-testid="slash-counter" className="font-mono tabular-nums">
          {slash.filtered.length}/{slash.total}
        </span>
      </div>
      <ul className="max-h-56 overflow-y-auto py-1">
        {slash.filtered.map((c, i) => (
          <li key={c.name}>
            <button
              type="button"
              data-testid="slash-menu-item"
              data-selected={i === slash.index}
              onMouseEnter={() => slash.onIndex(i)}
              onClick={() => slash.onPick(c.name)}
              className={cn(
                "flex w-full items-baseline gap-2 px-2.5 py-1 text-start text-xs",
                i === slash.index && "bg-muted",
              )}
            >
              <span className="shrink-0 font-mono">/{c.name}</span>
              {c.description && (
                <span className="text-muted-foreground truncate">
                  {c.description}
                </span>
              )}
            </button>
          </li>
        ))}
        {slash.filtered.length === 0 && (
          <li className="text-muted-foreground px-2.5 py-1 text-xs">
            no command matches /{slash.query}
          </li>
        )}
      </ul>
    </div>
  );
}
