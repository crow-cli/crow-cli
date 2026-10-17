"use client";

import { memo, useEffect, useState, type ElementType } from "react";
import {
  AlignJustifyIcon,
  BanIcon,
  CheckIcon,
  ChevronDownIcon,
  LoaderIcon,
  XCircleIcon,
} from "lucide-react";
import {
  ACP_COMPACTION_PART,
  isCompactionOpen,
  type AcpCompaction,
} from "@assistant-ui/acp";
import {
  TextMessagePartProvider,
  type AssistantDataUIProps,
  type DataMessagePartComponent,
  type DataMessagePartProps,
} from "@assistant-ui/react";
import { MarkdownText } from "@/components/assistant-ui/elements/markdown-text";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { useCollapseAll } from "@/lib/collapse-all";
import {
  compactionHeading,
  firstSummaryLine,
  type CompactionTone,
} from "@/lib/compaction";
import { cn } from "@/lib/utils";

/**
 * Context compaction, drawn: crow-client's `CellKind::Compaction` transcript
 * cell in webview clothes. One line says what the agent did to the context —
 * spinning while the pass runs, a receipt carrying its duration and the lines
 * it kept once it settles — and the retained summary rides behind it, because
 * that summary is the handoff that replaced this session's history and is the
 * only way to read what the model now remembers. Without the card the context
 * meter just falls with nothing to say why.
 *
 * The body is open while the pass runs, so the stream paints under the ticking
 * header exactly as the TUI does, and closes itself the moment the pass
 * settles: a finished compaction is a fact about the context, not something to
 * read. Anyone who toggled it by hand wins over that.
 */

const ANIMATION_DURATION = 200;

/** The TUI's `≡` heads every settled compaction; here only an unknown status
 * keeps it, the rest reading as the tool cards beside them do. */
const STATUS_ICON: Record<string, ElementType> = {
  in_progress: LoaderIcon,
  completed: CheckIcon,
  failed: XCircleIcon,
  cancelled: BanIcon,
};

/** crow-client colors the receipt by outcome: `theme.err`, `theme.warn_soft()`,
 * `theme.caption` — and the running line by its spinner, not its color. */
const TONE_CLASS: Record<CompactionTone, string> = {
  active: "text-muted-foreground",
  settled: "text-muted-foreground",
  cancelled: "text-warning",
  failed: "text-destructive",
};

const SPIN = "animate-spin [animation-duration:0.6s]";

/**
 * `Date.now()` once a second, but only while something is counting. A settled
 * card's duration is frozen at `endedAt`, and ticking there would re-render
 * the thread forever — assistant-ui's `useToolCallElapsed` gates its interval
 * the same way.
 */
function useTickingNow(running: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!running) return;
    setNow(Date.now());
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [running]);
  return now;
}

const HEADER_CLASS =
  "text-muted-foreground hover:text-foreground flex w-full min-w-0 items-center gap-2 rounded py-1.5 pe-1 ps-1 text-start transition-[color,scale] active:scale-[0.99]";

const CompactionCardImpl = ({ data }: DataMessagePartProps<AcpCompaction>) => {
  const running = isCompactionOpen(data.status);
  const now = useTickingNow(running);
  const heading = compactionHeading(data, now);
  const summary = data.summary;
  // No retained summary means no body, and a disclosure with nothing behind it
  // is a chevron that lies.
  const hasBody = summary.trim() !== "";
  const collapsedAll = useCollapseAll();
  // `null` is "untouched": the card follows the pass until a human disagrees.
  const [toggled, setToggled] = useState<boolean | null>(null);
  const [peek, setPeek] = useState(false);
  const open = hasBody && (toggled ?? running);
  const Icon = STATUS_ICON[data.status] ?? AlignJustifyIcon;
  const tone = TONE_CLASS[heading.tone];

  const row = (
    <>
      <Icon
        data-slot="compaction-icon"
        className={cn("size-4 shrink-0", tone, running && SPIN)}
        aria-hidden
      />
      <span
        data-testid="compaction-heading"
        className={cn("min-w-0 flex-1 truncate text-xs", tone)}
      >
        {heading.text}
      </span>
    </>
  );

  // collapse-all: the receipt on one line, with the first line of what was
  // retained as the peek. Clicking opens this one card without expanding the
  // rest; closing it returns to the line.
  if (collapsedAll && !peek) {
    const line = firstSummaryLine(summary);
    return (
      <button
        type="button"
        data-testid="compaction-collapsed"
        data-status={data.status}
        title="Expand this compaction"
        onClick={() => {
          setPeek(true);
          setToggled(true);
        }}
        className="text-muted-foreground hover:text-foreground flex w-full min-w-0 items-center gap-2 rounded py-0.5 ps-1 text-start text-xs transition-colors"
      >
        <Icon className={cn("size-3.5 shrink-0", tone, running && SPIN)} aria-hidden />
        <span className={cn("min-w-0 truncate", tone)}>{heading.text}</span>
        {line && <span className="min-w-0 truncate opacity-70">{line}</span>}
      </button>
    );
  }

  if (!hasBody) {
    return (
      <div
        data-slot="compaction-card"
        data-status={data.status}
        className={cn(
          HEADER_CLASS,
          "hover:text-muted-foreground py-0.5 cursor-default active:scale-100",
        )}
      >
        {row}
      </div>
    );
  }

  return (
    <Collapsible
      data-slot="compaction-card"
      data-status={data.status}
      open={open}
      onOpenChange={(next) => {
        setToggled(next);
        if (!next && collapsedAll) setPeek(false);
      }}
      className="group/compaction w-full py-0.5"
      style={
        {
          "--animation-duration": `${ANIMATION_DURATION}ms`,
        } as React.CSSProperties
      }
    >
      <CollapsibleTrigger
        data-slot="compaction-trigger"
        title={heading.text}
        className={cn(HEADER_CLASS, "group/trigger min-w-0")}
      >
        {row}
        <ChevronDownIcon
          data-slot="compaction-chevron"
          className={cn(
            "text-muted-foreground size-4 shrink-0 transition-transform duration-(--animation-duration) ease-[cubic-bezier(0.32,0.72,0,1)] motion-reduce:transition-none",
            "-rotate-90 group-data-open/trigger:rotate-0",
          )}
          aria-hidden
        />
      </CollapsibleTrigger>
      <CollapsibleContent
        data-slot="compaction-content"
        aria-busy={running}
        className={cn(
          "relative overflow-hidden text-sm outline-none",
          "ease-[cubic-bezier(0.32,0.72,0,1)] motion-reduce:animate-none",
          "data-closed:animate-collapsible-up data-open:animate-collapsible-down",
          "data-closed:fill-mode-forwards data-closed:pointer-events-none",
          "[--tw-duration:var(--animation-duration)]",
        )}
      >
        {/* The summary is prose the model wrote, so it renders as markdown —
            but it is a string this component holds, not a text part of the
            message, hence the provider that makes it one. */}
        <div
          data-slot="compaction-summary"
          className="border-foreground/10 ms-2 border-s ps-4 py-1"
        >
          <TextMessagePartProvider text={summary} isRunning={running}>
            <MarkdownText />
          </TextMessagePartProvider>
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
};

export const CompactionCard = memo(
  CompactionCardImpl,
) as DataMessagePartComponent<AcpCompaction>;
CompactionCard.displayName = "CompactionCard";

/**
 * The registration a host hands `useAssistantDataUI` to draw compactions.
 * Module level on purpose: the hook re-registers whenever `name` or `render`
 * moves identity, so an inline literal would churn the registry every render.
 */
export const COMPACTION_DATA_UI: AssistantDataUIProps<AcpCompaction> = {
  name: ACP_COMPACTION_PART,
  render: CompactionCard,
};
