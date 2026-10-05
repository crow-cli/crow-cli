import { useAcpUsage } from "@assistant-ui/acp";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { fmtTokens, usageFraction } from "@/lib/tokens";
import { cn } from "@/lib/utils";

// crow-cli fills `usage_update.size` with `max_compact_tokens_for(...)`, i.e.
// the compaction threshold — not the model's context window. crow-client says
// the same thing about its own ContextUsage ("tokens currently in context
// against the agent's compaction ceiling"), so the tooltip says it out loud
// rather than letting "ctx" imply a window.
const TONE = (pct: number) =>
  pct >= 90
    ? "text-destructive"
    : pct >= 70
      ? "text-warning"
      : "text-muted-foreground";

/**
 * The TUI status bar's `ctx 8.1K/180.0K 4%`. Renders nothing until the agent
 * has sent a `usage_update` carrying a real ceiling: a meter with no ceiling
 * would only be able to say `0/0 0%`, which reads as data.
 */
export function ContextMeter({ className }: { className?: string }) {
  const usage = useAcpUsage();
  if (!usage || !(usage.size > 0)) return null;

  const used = fmtTokens(usage.used);
  const size = fmtTokens(usage.size);
  const pct = Math.round(usageFraction(usage.used, usage.size) * 100);
  const cost = usage.cost;

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          data-testid="context-meter"
          data-pct={pct}
          className={cn(
            "shrink-0 font-mono text-xs tabular-nums",
            TONE(pct),
            className,
          )}
        >
          ctx {used}/{size} {pct}%
        </span>
      </TooltipTrigger>
      <TooltipContent side="bottom" align="end" className="max-w-64">
        <span>
          {used} of {size} tokens before crow-cli compacts this session. The
          ceiling is the agent's compaction threshold, not the model's context
          window.
          {cost ? ` Cost so far: ${cost.amount} ${cost.currency}.` : ""}
        </span>
      </TooltipContent>
    </Tooltip>
  );
}
