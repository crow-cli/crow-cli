import { useState } from "react";
import { CheckIcon, CopyIcon } from "lucide-react";
import { useAcpSessionId, useAcpSessionTitle } from "@assistant-ui/acp";
import { useAuiState } from "@assistant-ui/react";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

/**
 * The TUI prints `· session · <title>` and puts the wire session id in its
 * startup banner; here both ride the header. The title prefers whatever the
 * agent says (`session_info_update`) and falls back to the title the agent
 * derives for `session/list` — both are the agent's data, never invented
 * client-side. The id is truncated for the eye but the copy button and the
 * tooltip carry the whole thing.
 */
export function SessionBadge({ className }: { className?: string }) {
  const sessionId = useAcpSessionId();
  const agentTitle = useAcpSessionTitle();
  const listTitle = useAuiState((s) =>
    sessionId === undefined
      ? undefined
      : s.threads.threadItems.find((t) => t.id === sessionId)?.title,
  );
  const [copied, setCopied] = useState(false);
  if (!sessionId) return null;

  const title = agentTitle ?? listTitle;
  const copy = () => {
    void navigator.clipboard.writeText(sessionId).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1200);
    });
  };

  return (
    <span className={cn("flex min-w-0 items-center gap-1.5", className)}>
      <span aria-hidden className="text-muted-foreground/50">
        ·
      </span>
      {title && (
        <span
          data-testid="session-title"
          className="text-muted-foreground min-w-0 truncate text-xs"
        >
          {title}
        </span>
      )}
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            data-testid="session-id"
            data-session-id={sessionId}
            onClick={copy}
            aria-label={`Copy session id ${sessionId}`}
            className="text-muted-foreground hover:text-foreground flex shrink-0 items-center gap-1 rounded px-1 font-mono text-[11px] tabular-nums"
          >
            {sessionId.slice(0, 8)}…{sessionId.slice(-4)}
            {copied ? (
              <CheckIcon className="text-success size-3" />
            ) : (
              <CopyIcon className="size-3" />
            )}
          </button>
        </TooltipTrigger>
        <TooltipContent side="bottom" className="font-mono">
          {copied ? "Copied" : sessionId}
        </TooltipContent>
      </Tooltip>
    </span>
  );
}
