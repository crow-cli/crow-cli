import { isCompactionOpen, type AcpCompaction } from "@assistant-ui/acp";

/**
 * The compaction card's derived text, kept out of the component so the labels
 * are testable and so the card and crow-client's transcript cell cannot drift:
 * every string here has a twin in `crates/crow-client/src/transcript.rs`'s
 * `CellKind::Compaction` arm.
 */

export type CompactionTone = "active" | "settled" | "cancelled" | "failed";

export type CompactionHeading = {
  /** The one-line receipt, duration and lines-kept included. */
  readonly text: string;
  readonly tone: CompactionTone;
  /** True only while the pass has not reached a terminal state. */
  readonly open: boolean;
};

const receipt = (label: string, ...rest: (string | undefined)[]) =>
  [label, ...rest].filter((part): part is string => !!part).join(" · ");

/**
 * A duration: `<1s` under a second, `3.2s` under a minute, `2m 5s` over — the
 * tool card's `formatElapsed`, so a compaction reads like the call beside it.
 */
export function formatDuration(ms: number): string {
  if (!Number.isFinite(ms) || ms < 1000) return "<1s";
  const seconds = ms / 1000;
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  return `${Math.floor(seconds / 60)}m ${Math.floor(seconds % 60)}s`;
}

/**
 * How long the pass has taken. Ticks against `now` while open and freezes at
 * `endedAt` once it settles, which is what lets one header do both.
 */
export function compactionElapsed(c: AcpCompaction, now: number): number {
  return Math.max(0, (c.endedAt ?? now) - c.startedAt);
}

/**
 * Non-blank lines in the retained summary — the receipt's `· 12 lines`. Zero
 * means the agent compacted without streaming or reporting what it kept, so
 * quoting "0 lines" would be noise and the caller leaves it out.
 */
export function summaryLines(summary: string): number {
  if (!summary.trim()) return 0;
  return summary.split("\n").filter((line) => line.trim() !== "").length;
}

/**
 * The first non-blank line of the retained summary — what collapse-all shows
 * beside the receipt, the same one-line peek the reasoning disclosure gives a
 * closed thought. `undefined` when nothing was retained.
 */
export function firstSummaryLine(summary: string): string | undefined {
  return summary.split("\n").find((line) => line.trim() !== "")?.trim();
}

/** The card's one line, for a compaction observed at `now`. */
export function compactionHeading(
  c: AcpCompaction,
  now: number,
): CompactionHeading {
  if (isCompactionOpen(c.status)) {
    return { text: "Compacting context…", tone: "active", open: true };
  }
  const dur = formatDuration(compactionElapsed(c, now));
  switch (c.status) {
    case "failed":
      return {
        text: receipt("Compaction failed", c.error || "unknown"),
        tone: "failed",
        open: false,
      };
    case "cancelled":
      return {
        text: receipt("Compaction cancelled", dur),
        tone: "cancelled",
        open: false,
      };
    case "completed": {
      const lines = summaryLines(c.summary);
      return {
        text: receipt(
          "Context compacted",
          dur,
          lines ? `${lines} line${lines === 1 ? "" : "s"}` : undefined,
        ),
        tone: "settled",
        open: false,
      };
    }
    default:
      // A status this client has not heard of reads as SETTLED: an unrecognized
      // terminal status is a cosmetic miss, while treating it as in-progress
      // strands the card spinning forever on a pass that is over.
      return {
        text: receipt(`Compaction ${c.status}`, dur),
        tone: "settled",
        open: false,
      };
  }
}
