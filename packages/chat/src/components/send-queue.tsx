import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
  type RefObject,
} from "react";
import {
  ComposerPrimitive,
  useAui,
  useAuiState,
  type AppendMessage,
  type QueueItemState,
} from "@assistant-ui/react";
import { TooltipIconButton } from "@/components/assistant-ui/elements/tooltip-icon-button";
import { cn } from "@/lib/utils";
import { CheckIcon, Trash2Icon, ZapIcon } from "lucide-react";

/**
 * The TUI's `queue_previews`: text blocks whitespace-collapsed and joined,
 * anything else named as a file, and an item with nothing in it saying so
 * rather than rendering as a blank row.
 */
export const queueSummary = (item: QueueItemState): string => {
  const pieces: string[] = [];
  for (const part of item.parts) {
    if (part.type === "text") {
      const text = part.text.split(/\s+/).filter(Boolean).join(" ");
      if (text) pieces.push(text);
    } else {
      pieces.push(`▣ ${part.filename ?? part.mimeType}`);
    }
  }
  return pieces.length === 0 ? "empty prompt" : pieces.join(" ");
};

/**
 * The TUI's `queue_selection` + `QueueEditState` as one value: which row the
 * chooser is on, or which row's text the composer is holding for an edit.
 */
export type QueueEditor =
  | { mode: "select"; index: number }
  | { mode: "edit"; id: string; deleteConfirm: boolean }
  | null;

/** What an edit loads into the composer: the row's text, not its summary. */
const queueText = (item: QueueItemState) =>
  item.parts
    .filter((part) => part.type === "text")
    .map((part) => part.text)
    .join("\n");

/**
 * The saved row goes back as the same kind of message the queue holds: the
 * edited text plus whatever non-text parts the row already carried, so an
 * attachment survives its prompt being rewritten.
 */
const editedMessage = (
  lastMessageId: string | null,
  item: QueueItemState,
  text: string,
): AppendMessage => ({
  role: "user",
  content: [
    ...(text ? [{ type: "text" as const, text }] : []),
    ...item.parts.filter((part) => part.type !== "text"),
  ],
  attachments: [],
  createdAt: new Date(),
  metadata: { custom: {} },
  parentId: lastMessageId,
  sourceId: null,
  runConfig: undefined,
});

const NOTICE_MS = 4000;

export type QueueEditorApi = {
  editor: QueueEditor;
  /** The shelf's hint slot: a transient notice, else what the keys do now. */
  hint: string;
  placeholder: string;
  inputRef: RefObject<HTMLTextAreaElement | null>;
  onKeyDown: (event: KeyboardEvent<Element>) => void;
  select: (index: number) => void;
  beginEdit: (id: string) => void;
  save: () => void;
  armDelete: () => void;
  remove: (id: string) => void;
};

/**
 * The `alt+↑` twin of the TUI's queue editor (`open_queue_selector`,
 * `begin_queue_edit_at`, `save_queue_edit`, `delete_queue_edit`): a chooser over
 * the queued rows, Enter loads a row into the composer and marks it edited,
 * Enter saves it back into the same slot, ctrl+d arms a delete, Esc backs out
 * one step at a time. The notices are the TUI's own tip strings.
 */
export function useQueueEditor(): QueueEditorApi {
  const aui = useAui();
  const queue = useAuiState((s) => s.composer.queue);
  // The TUI's hint dock is a state machine over (run state × draft): what
  // Enter does right now, and how to steer instead of queueing.
  const running = useAuiState((s) => s.thread.isRunning);
  const draft = useAuiState((s) => !s.composer.isEmpty);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const [editor, setEditor] = useState<QueueEditor>(null);
  const [notice, setNotice] = useState<string | null>(null);
  // alt+↑ arrives on a window listener and the key router runs between
  // renders, so both read the editor through a ref every transition updates.
  const editorRef = useRef<QueueEditor>(null);
  const noticeTimer = useRef<number | undefined>(undefined);

  const apply = useCallback((next: QueueEditor) => {
    editorRef.current = next;
    setEditor(next);
  }, []);

  const say = useCallback((text: string) => {
    setNotice(text);
    window.clearTimeout(noticeTimer.current);
    noticeTimer.current = window.setTimeout(() => setNotice(null), NOTICE_MS);
  }, []);

  useEffect(() => () => window.clearTimeout(noticeTimer.current), []);

  const rows = useCallback(() => aui.composer.getState().queue, [aui]);

  /** End an edit and drop the draft it was holding. */
  const drop = useCallback(
    (text: string) => {
      aui.composer.setText("");
      apply(null);
      say(text);
    },
    [aui, apply, say],
  );

  const beginEdit = useCallback(
    (id: string) => {
      const item = rows().find((row) => row.id === id);
      if (!item) {
        apply(null);
        say("queued prompt already left the queue");
        return;
      }
      aui.composer.setText(queueText(item));
      apply({ mode: "edit", id, deleteConfirm: false });
      inputRef.current?.focus();
    },
    [apply, aui, rows, say],
  );

  const open = useCallback(() => {
    if (editorRef.current) return;
    const composer = aui.composer.getState();
    // An empty queue has no shelf to choose from and nowhere to say so.
    if (composer.queue.length === 0) return;
    if (!composer.isEmpty) {
      say("send or clear the draft before editing the queue");
      return;
    }
    apply({ mode: "select", index: composer.queue.length - 1 });
    inputRef.current?.focus();
  }, [apply, aui, say]);

  const select = useCallback(
    (index: number) => {
      // A click while the composer holds a row's text is not a re-selection.
      if (editorRef.current?.mode === "edit") return;
      apply({ mode: "select", index });
      // The chooser's keys live on the composer, so a mouse click hands focus
      // back to it: enter on the row the click just marked.
      inputRef.current?.focus();
    },
    [apply],
  );

  const remove = useCallback(
    (id: string) => {
      const before = rows();
      const index = before.findIndex((row) => row.id === id);
      if (index === -1) {
        apply(null);
        say("queued prompt already left the queue");
        return;
      }
      aui.composer.queueItem({ id }).remove();
      const current = editorRef.current;
      if (current?.mode === "edit") {
        if (current.id === id) drop(`queued prompt ${index + 1} deleted`);
        else say(`queued prompt ${index + 1} deleted`);
        return;
      }
      if (current?.mode === "select") {
        const left = before.length - 1;
        apply(
          left === 0
            ? null
            : { mode: "select", index: Math.min(current.index, left - 1) },
        );
      }
      say(`queued prompt ${index + 1} deleted`);
    },
    [apply, aui, drop, rows, say],
  );

  const armDelete = useCallback(() => {
    const current = editorRef.current;
    if (current?.mode !== "edit" || current.deleteConfirm) return;
    apply({ ...current, deleteConfirm: true });
    say("delete queued prompt? · enter confirm · esc back");
  }, [apply, say]);

  const save = useCallback(() => {
    const current = editorRef.current;
    if (current?.mode !== "edit") return;
    if (current.deleteConfirm) {
      remove(current.id);
      return;
    }
    const composer = aui.composer.getState();
    const index = composer.queue.findIndex((row) => row.id === current.id);
    if (index === -1) {
      drop("queued prompt already left the queue");
      return;
    }
    const item = composer.queue[index]!;
    const text = composer.text.trim();
    if (!text && item.parts.every((part) => part.type === "text")) {
      say("queued prompt cannot be empty · ctrl+d deletes it");
      return;
    }
    aui.composer
      .queueItem({ id: item.id })
      .edit(
        editedMessage(
          aui.thread.getState().messages.at(-1)?.id ?? null,
          item,
          text,
        ),
      );
    aui.composer.setText("");
    apply(null);
    say(`queued prompt ${index + 1} updated`);
  }, [apply, aui, drop, remove, say]);

  const cancelEdit = useCallback(() => {
    const current = editorRef.current;
    if (current?.mode !== "edit") return;
    if (current.deleteConfirm) {
      apply({ ...current, deleteConfirm: false });
      say("delete cancelled · still editing queued prompt");
      return;
    }
    drop("queued prompt edit cancelled");
  }, [apply, drop, say]);

  // alt+↑ opens the chooser wherever focus is, the way the TUI binds it
  // globally; a browser has no single input line to own the chord.
  useEffect(() => {
    const onKey = (event: globalThis.KeyboardEvent) => {
      if (!event.altKey || event.key !== "ArrowUp") return;
      event.preventDefault();
      open();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  // The web queue keeps draining while the chooser is open (the TUI pauses
  // its own), so a row can leave underneath it: the selection follows the
  // rows that remain, and an edit whose row went out ends with the TUI's note.
  useEffect(() => {
    if (!editor) return;
    if (editor.mode === "select") {
      if (queue.length === 0) apply(null);
      else if (editor.index >= queue.length)
        apply({ mode: "select", index: queue.length - 1 });
      return;
    }
    if (!queue.some((item) => item.id === editor.id))
      drop("queued prompt already left the queue");
  }, [apply, drop, editor, queue]);

  const onKeyDown = useCallback(
    (event: KeyboardEvent<Element>) => {
      const current = editorRef.current;
      if (!current || event.nativeEvent.isComposing) return;
      if (event.key === "Escape") {
        event.preventDefault();
        if (current.mode === "select") {
          apply(null);
          say("queue selection closed");
        } else {
          cancelEdit();
        }
        return;
      }
      if (current.mode === "select") {
        const count = rows().length;
        if (count === 0) {
          apply(null);
          return;
        }
        if (event.key === "ArrowUp" || event.key === "ArrowDown") {
          event.preventDefault();
          const step = event.key === "ArrowUp" ? -1 : 1;
          apply({
            mode: "select",
            index: (current.index + step + count) % count,
          });
          return;
        }
        if (event.key === "Enter" && !event.shiftKey) {
          event.preventDefault();
          const item = rows()[Math.min(current.index, count - 1)];
          if (item) beginEdit(item.id);
          return;
        }
        // Typing ends the chooser and lands in the composer: a textarea that
        // swallows keystrokes would be a lie the TUI does not have to tell.
        if (event.key.length === 1 && !event.ctrlKey && !event.metaKey)
          apply(null);
        return;
      }
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        save();
        return;
      }
      if (event.key === "d" && event.ctrlKey) {
        event.preventDefault();
        armDelete();
      }
    },
    [apply, armDelete, beginEdit, cancelEdit, rows, save, say],
  );

  const editing = editor?.mode === "edit" ? editor : undefined;
  const ordinal = editing
    ? queue.findIndex((item) => item.id === editing.id) + 1
    : 0;
  const hint =
    notice ??
    (editing
      ? editing.deleteConfirm
        ? "enter delete · esc back"
        : "enter save · ctrl+d delete · esc cancel"
      : editor?.mode === "select"
        ? "↑/↓ choose · enter edit · esc close"
        : running && draft
          ? "enter queues · ctrl+enter steers now"
          : "enter sends first · alt+↑ edit");
  const placeholder = editing
    ? `editing queued prompt ${ordinal} · enter saves`
    : editor?.mode === "select"
      ? "choose a queued prompt · ↑/↓ · enter edit"
      : running
        ? queue.length > 0
          ? "queued · empty enter sends first · ctrl+enter steers now"
          : "queue a follow-up — ctrl+enter steers now"
        : "Send a message...";

  return {
    editor,
    hint,
    placeholder,
    inputRef,
    onKeyDown,
    select,
    beginEdit,
    save,
    armDelete,
    remove,
  };
}

/**
 * The TUI's queue shelf (`ui.rs::draw_queue_shelf`), docked above the
 * composer: `▎Queue · N` over one `› {ordinal}  {summary}` row per pending
 * prompt, plus the hint slot saying what the keys do right now. It renders the
 * composer's own queue, so what is on screen is exactly what the runtime will
 * send, in the order it will send it. Row markers are the TUI's — `×` armed
 * for deletion, `✎` the row the composer is editing, `▸` the chooser's row,
 * `›` the rest — and every row carries the mouse twin of the two edits: `✎`
 * loads it into the composer, `×` drops it.
 */
export function SendQueue({ editor }: { editor: QueueEditorApi }) {
  const queue = useAuiState((s) => s.composer.queue);
  const ordinals = useMemo(
    () => new Map(queue.map((item, index) => [item.id, index + 1])),
    [queue],
  );
  if (queue.length === 0) return null;
  const editing = editor.editor?.mode === "edit" ? editor.editor : undefined;
  const selecting =
    editor.editor?.mode === "select" ? editor.editor : undefined;

  return (
    <div
      data-testid="queue-panel"
      data-slot="aui_composer-queue"
      data-choosing={editor.editor ? "true" : undefined}
      className="bg-muted/50 border-foreground/10 text-muted-foreground -mb-4 flex flex-col gap-1 rounded-t-(--composer-radius) border border-b-0 px-4 pt-2 pb-7 font-mono text-xs"
    >
      <div className="flex items-baseline gap-1.5">
        <span aria-hidden className="text-primary font-bold">
          {"▎"}
        </span>
        <span
          data-testid="queue-count"
          className="text-foreground font-bold tabular-nums"
        >
          Queue · {queue.length}
        </span>
        <span
          data-testid="queue-hint"
          className="text-muted-foreground/60 min-w-0 flex-1 truncate"
        >
          · {editor.hint}
        </span>
      </div>
      <ComposerPrimitive.Queue>
        {({ queueItem }) => {
          const ordinal = ordinals.get(queueItem.id) ?? 1;
          const isEditing = editing?.id === queueItem.id;
          const confirming = isEditing && editing?.deleteConfirm === true;
          const isSelected = selecting?.index === ordinal - 1;
          const marker = confirming
            ? "×"
            : isEditing
              ? "✎"
              : isSelected
                ? "▸"
                : "›";
          return (
            <div
              data-testid="queue-row"
              data-queue-item-id={queueItem.id}
              data-editing={isEditing ? "true" : undefined}
              data-selected={isSelected ? "true" : undefined}
              onClick={() => editor.select(ordinal - 1)}
              className={cn(
                "-mx-1 flex min-w-0 cursor-pointer items-baseline gap-1.5 rounded-sm px-1",
                confirming
                  ? "text-destructive"
                  : isEditing
                    ? "text-warning"
                    : isSelected
                      ? "text-primary"
                      : "text-muted-foreground",
              )}
            >
              <span
                data-testid="queue-row-marker"
                aria-hidden
                className={cn(
                  "shrink-0 font-bold",
                  !isEditing && !isSelected && ordinal === 1 && "text-primary",
                )}
              >
                {marker}
              </span>
              <span className="shrink-0 tabular-nums">{ordinal}</span>
              <span
                className="min-w-0 flex-1 truncate"
                title={queueSummary(queueItem)}
              >
                {queueSummary(queueItem)}
              </span>
              <span
                className="flex shrink-0 items-center gap-1"
                onClick={(event) => event.stopPropagation()}
              >
                <button
                  type="button"
                  data-testid="queue-row-edit"
                  aria-label={`Edit queued prompt ${ordinal}`}
                  title="Edit this queued prompt"
                  onClick={() => editor.beginEdit(queueItem.id)}
                  className="text-muted-foreground/50 hover:text-warning focus-visible:text-warning transition-colors"
                >
                  {"✎"}
                </button>
                <button
                  type="button"
                  data-testid="queue-row-delete"
                  aria-label={`Delete queued prompt ${ordinal}`}
                  title="Delete this queued prompt"
                  onClick={() => editor.remove(queueItem.id)}
                  className="text-muted-foreground/50 hover:text-destructive focus-visible:text-destructive transition-colors"
                >
                  {"×"}
                </button>
              </span>
            </div>
          );
        }}
      </ComposerPrimitive.Queue>
    </div>
  );
}

/**
 * The action row while the composer holds a queued prompt: save the edit, or
 * delete the row — armed on the first click and confirmed on the second, the
 * mouse twin of the TUI's `ctrl+d` then `enter`. Send is gone for the
 * duration, because a send here would queue a second copy of the row being
 * edited rather than saving it.
 */
export function QueueEditControls({ editor }: { editor: QueueEditorApi }) {
  const state = editor.editor;
  if (state?.mode !== "edit") return null;
  const armed = state.deleteConfirm;

  return (
    <div
      data-testid="queue-edit-controls"
      className="flex shrink-0 items-center gap-1.5"
    >
      <TooltipIconButton
        tooltip={armed ? "Confirm delete" : "Delete queued prompt"}
        side="bottom"
        type="button"
        variant="ghost"
        size="icon"
        data-testid="queue-edit-delete"
        data-armed={armed ? "true" : undefined}
        aria-label={armed ? "Confirm delete" : "Delete queued prompt"}
        className={cn(
          "size-7 rounded-full",
          armed ? "text-destructive" : "text-muted-foreground hover:text-destructive",
        )}
        onClick={armed ? () => editor.remove(state.id) : editor.armDelete}
      >
        <Trash2Icon className="size-4" />
      </TooltipIconButton>
      <TooltipIconButton
        tooltip="Save queued prompt"
        side="bottom"
        type="button"
        variant="default"
        size="icon"
        data-testid="queue-edit-save"
        aria-label="Save queued prompt"
        className="size-7 rounded-full"
        onClick={editor.save}
      >
        <CheckIcon className="size-4" />
      </TooltipIconButton>
    </div>
  );
}

/**
 * The mouse twin of the TUI's `ctrl+enter` Send Now (`app/send_queue.rs::
 * send_now`): the draft goes out as its own `session/prompt` immediately,
 * while the turn in flight keeps running, and gets its own reply when the
 * agent reaches it. It only appears while a run is in flight — idle, it would
 * be a second Send button meaning the same thing as the first.
 */
export function SendNowButton() {
  const aui = useAui();
  const show = useAuiState(
    (s) =>
      s.thread.isRunning &&
      s.thread.capabilities.queue &&
      !s.composer.isEmpty &&
      s.composer.canSend,
  );
  if (!show) return null;

  return (
    <TooltipIconButton
      tooltip="Send now · ctrl+enter"
      side="bottom"
      type="button"
      variant="ghost"
      size="icon"
      data-testid="send-now"
      aria-label="Send now"
      className="text-warning hover:text-warning size-7 rounded-full"
      onClick={() => aui.composer.send({ steer: true })}
    >
      <ZapIcon data-testid="send-now-icon" className="size-4" />
    </TooltipIconButton>
  );
}

/**
 * The TUI's working row (`● working 12s · 2 queued`) minus the
 * elapsed seconds: a pill in the composer's action row saying the agent is
 * busy and how many prompts wait behind it. Nothing renders while the thread
 * is idle, so an empty queue costs no chrome.
 */
export function WorkingIndicator({ className }: { className?: string }) {
  const isRunning = useAuiState((s) => s.thread.isRunning);
  const queued = useAuiState((s) => s.composer.queue.length);
  if (!isRunning) return null;

  return (
    <span
      data-testid="working-indicator"
      className={cn(
        "text-muted-foreground flex min-w-0 items-center gap-1.5 font-mono text-xs",
        className,
      )}
    >
      <span
        aria-hidden
        className="text-primary animate-pulse motion-reduce:animate-none"
      >
        {"●"}
      </span>
      <span className="text-primary shrink-0">working</span>
      {queued > 0 && (
        <span
          data-testid="queued-count"
          className="text-warning shrink-0 tabular-nums"
        >
          · {queued} queued
        </span>
      )}
    </span>
  );
}
