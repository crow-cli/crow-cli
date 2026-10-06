import { useCallback, useEffect, useRef, useState } from "react";
import { useAui } from "@assistant-ui/react";
import { BookOpenIcon, CircleHelpIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { chatTranscript } from "@/lib/chat-transcript";

export function ChatAccessibility({ verbosity }: { verbosity: boolean }) {
  const aui = useAui();
  const [view, setView] = useState<"help" | "transcript" | null>(null);
  const [transcript, setTranscript] = useState("");
  const [hint, setHint] = useState(false);
  const previousFocus = useRef<HTMLElement | null>(null);
  useEffect(() => {
    const onFocus = () => setHint(true);
    document.addEventListener("focusin", onFocus);
    return () => document.removeEventListener("focusin", onFocus);
  }, []);
  const open = useCallback((next: "help" | "transcript") => {
    previousFocus.current = document.activeElement as HTMLElement;
    if (next === "transcript") setTranscript(chatTranscript(aui.thread.getState().messages));
    setView(next);
  }, [aui]);
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (!event.altKey || (event.key !== "F1" && event.key !== "F2")) return;
      event.preventDefault();
      event.stopPropagation();
      open(event.key === "F1" ? "help" : "transcript");
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [open]);
  return <>
    <span className="sr-only" role="status">{verbosity && hint ? "Press Alt+F1 for chat accessibility help or Alt+F2 for the plain-text transcript." : ""}</span>
    <Button variant="ghost" size="icon" aria-label="Chat accessibility help" title="Chat accessibility help · Alt+F1" onClick={() => open("help")}><CircleHelpIcon className="size-4" /></Button>
    <Button variant="ghost" size="icon" aria-label="Read chat transcript" title="Read chat transcript · Alt+F2" onClick={() => open("transcript")}><BookOpenIcon className="size-4" /></Button>
    <Dialog open={view !== null} onOpenChange={(isOpen) => { if (!isOpen) setView(null); }}>
      <DialogContent className="sm:max-w-2xl" onCloseAutoFocus={(event) => { event.preventDefault(); previousFocus.current?.focus(); }}>
        <DialogTitle>{view === "help" ? "Chat Accessibility Help" : "Chat Transcript"}</DialogTitle>
        <DialogDescription>{view === "help" ? "Keyboard navigation and chat actions." : "A read-only snapshot of messages, thoughts and tool results, including diffs."}</DialogDescription>
        {view === "help" ? <ul className="list-disc space-y-2 pl-5">
          <li>Tab and Shift+Tab move between thread history, model selection, tool cards and the composer.</li>
          <li>Enter sends a message, or queues it while the agent is working. Shift+Enter inserts a newline. Ctrl+Enter sends immediately to steer the current turn.</li>
          <li>Alt+Up selects queued messages. Up and Down select a row; Enter edits or saves it. Ctrl+D arms deletion; Escape backs out.</li>
          <li>Ctrl+Shift+O toggles all tool calls and thoughts. Individual tool cards toggle with Enter or Space.</li>
          <li>The Add Attachment button adds files. The Stop button cancels the current turn.</li>
          <li>Alt+F2 opens a plain-text transcript. Escape closes this dialog and restores focus.</li>
        </ul> : <textarea autoFocus readOnly aria-label="Chat transcript" className="h-[60vh] w-full resize-none rounded border bg-background p-3 font-mono text-sm" value={transcript || "No messages in this thread."} />}
      </DialogContent>
    </Dialog>
  </>;
}
