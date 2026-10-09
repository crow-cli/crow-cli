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

function useUsage() {
  const usage = useAcpUsage();
  if (!usage || !(usage.size > 0)) return null;
  return {
    used: fmtTokens(usage.used),
    size: fmtTokens(usage.size),
    pct: Math.round(usageFraction(usage.used, usage.size) * 100),
    cost: usage.cost,
  };
}

function MeterTooltip({ used, size, cost }: { used: string; size: string; cost?: { amount: number; currency: string } | null }) {
  return (
    <TooltipContent side="top" align="end" className="max-w-64">
      <span>
        {used} of {size} tokens before crow-cli compacts this session. The
        ceiling is the agent's compaction threshold, not the model's context
        window.
        {cost ? ` Cost so far: ${cost.amount} ${cost.currency}.` : ""}
      </span>
    </TooltipContent>
  );
}

/**
 * The TUI status bar's `ctx 8.1K/180.0K 4%`. Renders nothing until the agent
 * has sent a `usage_update` carrying a real ceiling: a meter with no ceiling
 * would only be able to say `0/0 0%`, which reads as data.
 */
export function ContextMeter({ className }: { className?: string }) {
  const usage = useUsage();
  if (!usage) return null;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          data-testid="context-meter"
          data-pct={usage.pct}
          className={cn(
            "shrink-0 font-mono text-xs tabular-nums",
            TONE(usage.pct),
            className,
          )}
        >
          ctx {usage.used}/{usage.size} {usage.pct}%
        </span>
      </TooltipTrigger>
      <MeterTooltip {...usage} />
    </Tooltip>
  );
}

const RING = 2 * Math.PI * 8;

/**
 * The meter as a pie gauge for the webview's footer, where the TUI-style
 * `ctx a/b c%` string would compete with the composer for width. The ring
 * fills clockwise from twelve o'clock; the tooltip carries the counts.
 */
export function ContextGauge({ className }: { className?: string }) {
  const usage = useUsage();
  if (!usage) return null;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          data-testid="context-meter"
          data-pct={usage.pct}
          aria-label={`Context ${usage.pct}%`}
          className={cn(
            "flex shrink-0 items-center gap-1.5 font-mono text-xs tabular-nums",
            TONE(usage.pct),
            className,
          )}
        >
          <svg viewBox="0 0 20 20" className="size-4" aria-hidden>
            <circle cx="10" cy="10" r="8" fill="none" stroke="currentColor" strokeWidth="3" className="opacity-25" />
            <circle
              cx="10"
              cy="10"
              r="8"
              fill="none"
              stroke="currentColor"
              strokeWidth="3"
              strokeLinecap="round"
              strokeDasharray={`${(usage.pct / 100) * RING} ${RING}`}
              transform="rotate(-90 10 10)"
            />
          </svg>
          {usage.pct}%
        </span>
      </TooltipTrigger>
      <MeterTooltip {...usage} />
    </Tooltip>
  );
}
