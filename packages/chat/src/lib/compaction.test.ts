/// <reference types="bun-types" />
import { describe, expect, it } from "bun:test";
import {
  EMPTY_ACP_THREAD_STATE,
  reduceAcpThreadState,
  type AcpAssistantMessage,
  type AcpThreadEvent,
  type AcpThreadState,
} from "../../../aui/acp/src/acpThreadState";
import {
  ACP_COMPACTION_PART,
  isCompactionPart,
} from "../../../aui/acp/src/compaction";
import type { AcpCompaction, AcpSessionUpdate } from "../../../aui/acp/src/types";
import {
  compactionElapsed,
  compactionHeading,
  firstSummaryLine,
  formatDuration,
  summaryLines,
} from "./compaction";

const assistant = (id: string): AcpAssistantMessage => ({
  role: "assistant",
  id,
  parentId: null,
  createdAt: 0,
  status: { type: "running" },
  content: [],
});

const reduce = (state: AcpThreadState, event: AcpThreadEvent) =>
  reduceAcpThreadState(state, event);

/** A thread with one live turn to write into. */
const running = (id = "a1") =>
  reduce(EMPTY_ACP_THREAD_STATE, { type: "run-start", message: assistant(id) });

const send = (state: AcpThreadState, update: AcpSessionUpdate) =>
  reduce(state, { type: "session-update", update });

const contentOf = (state: AcpThreadState, id: string) => {
  const message = state.messagesById[id];
  if (message?.role !== "assistant") throw new Error(`no assistant ${id}`);
  return message.content;
};

const partsIn = (state: AcpThreadState, id: string) =>
  contentOf(state, id).filter(isCompactionPart);

const compactionsIn = (state: AcpThreadState, id: string): AcpCompaction[] =>
  partsIn(state, id).map((part) => part.data);

const one = (state: AcpThreadState, id = "a1"): AcpCompaction => {
  const found = compactionsIn(state, id);
  expect(found).toHaveLength(1);
  return found[0]!;
};

const open = (id = "c1"): AcpSessionUpdate => ({
  sessionUpdate: "compaction_update",
  compactionId: id,
  status: "in_progress",
});

const chunk = (text: string, id = "c1"): AcpSessionUpdate => ({
  sessionUpdate: "compaction_summary_chunk",
  compactionId: id,
  content: { type: "text", text },
});

const settle = (
  status: string,
  extra?: { summary?: readonly { type: "text"; text: string }[] | null; error?: string | null },
  id = "c1",
): AcpSessionUpdate => ({
  sessionUpdate: "compaction_update",
  compactionId: id,
  status,
  ...extra,
});

const text = (t: string) => ({ type: "text", text: t }) as const;

describe("compaction reducer", () => {
  it("mints one data part on the first update and records where it lives", () => {
    const state = send(running(), open());
    expect(state.compactionMessages).toEqual({ c1: "a1" });
    const parts = partsIn(state, "a1");
    expect(parts).toHaveLength(1);
    expect(parts[0]!.type).toBe("data");
    expect(parts[0]!.name).toBe(ACP_COMPACTION_PART);
    expect(parts[0]!.id).toBe("c1");
    const c = parts[0]!.data;
    expect(c.status).toBe("in_progress");
    expect(c.summary).toBe("");
    expect(typeof c.startedAt).toBe("number");
    expect(c.endedAt ?? null).toBeNull();
  });

  it("treats a duplicate of the same update as a no-op", () => {
    const state = send(running(), open());
    expect(send(state, open())).toBe(state);
    const done = send(state, settle("completed"));
    expect(send(done, settle("completed"))).toBe(done);
  });

  it("ignores an update with no compaction id", () => {
    const state = running();
    expect(send(state, open(""))).toBe(state);
    expect(send(state, chunk("text", ""))).toBe(state);
  });

  it("appends streamed chunks into the same part", () => {
    let state = send(running(), open());
    state = send(state, chunk("kept: "));
    state = send(state, chunk("the plan\n"));
    expect(partsIn(state, "a1")).toHaveLength(1);
    expect(one(state).summary).toBe("kept: the plan\n");
    expect(one(state).status).toBe("in_progress");
  });

  it("ignores a chunk that carries no text", () => {
    const state = send(running(), open());
    const image = send(state, {
      sessionUpdate: "compaction_summary_chunk",
      compactionId: "c1",
      content: { type: "image", data: "aaa", mimeType: "image/png" },
    });
    expect(image).toBe(state);
  });

  it("mints the entity late when a chunk arrives before its update", () => {
    const state = send(running(), chunk("orphan text"));
    expect(state.compactionMessages).toEqual({ c1: "a1" });
    expect(one(state).status).toBe("in_progress");
    expect(one(state).summary).toBe("orphan text");
  });

  it("keeps what streamed when the terminal update carries no summary", () => {
    let state = send(running(), open());
    state = send(state, chunk("line one\nline two\n"));
    const done = send(state, settle("completed"));
    const c = one(done);
    expect(c.status).toBe("completed");
    expect(c.summary).toBe("line one\nline two\n");
    expect(typeof c.endedAt).toBe("number");
    expect(c.endedAt!).toBeGreaterThanOrEqual(c.startedAt);
  });

  it("replaces the summary when the terminal update reports one", () => {
    let state = send(running(), open());
    state = send(state, chunk("streamed prose"));
    const done = send(state, settle("completed", { summary: [text("a"), text("b")] }));
    // `concat_text_blocks`: the `.text` of every text block, in order.
    expect(one(done).summary).toBe("ab");
  });

  it("reads an empty summary list as the explicit clear", () => {
    let state = send(running(), open());
    state = send(state, chunk("streamed prose"));
    expect(one(send(state, settle("completed", { summary: [] }))).summary).toBe("");
    expect(one(send(state, settle("completed", { summary: null }))).summary).toBe("");
  });

  it("carries the error a failed pass reports", () => {
    const state = send(running(), settle("failed", { error: "model said no" }));
    const c = one(state);
    expect(c.status).toBe("failed");
    expect(c.error).toBe("model said no");
    // Terminal at first sight: it was replayed, not watched, so it settles at once.
    expect(c.endedAt).toBe(c.startedAt);
  });

  it("settles a status it does not recognize instead of spinning on it", () => {
    const state = send(running(), settle("_crow_paused"));
    const c = one(state);
    expect(c.status).toBe("_crow_paused");
    expect(typeof c.endedAt).toBe("number");
  });

  it("keeps two compactions in one turn apart, in arrival order", () => {
    let state = send(running(), open("c1"));
    state = send(state, open("c2"));
    state = send(state, chunk("one", "c1"));
    state = send(state, chunk("two", "c2"));
    state = send(state, settle("completed", undefined, "c1"));
    expect(state.compactionMessages).toEqual({ c1: "a1", c2: "a1" });
    expect(compactionsIn(state, "a1").map((c) => [c.id, c.summary, c.status])).toEqual([
      ["c1", "one", "completed"],
      ["c2", "two", "in_progress"],
    ]);
  });

  it("settles an open pass when the turn ends", () => {
    let state = send(running(), open());
    state = send(state, chunk("partial"));
    const ended = reduce(state, {
      type: "run-end",
      status: { type: "complete", reason: "stop" },
    });
    const c = one(ended);
    expect(c.status).toBe("failed");
    expect(c.error).toBe("turn ended");
    expect(c.summary).toBe("partial");
    expect(typeof c.endedAt).toBe("number");
  });

  it("settles an open pass as cancelled when the turn was cancelled", () => {
    const state = send(running(), open());
    const ended = reduce(state, {
      type: "run-end",
      status: { type: "incomplete", reason: "cancelled" },
    });
    expect(one(ended).status).toBe("cancelled");
    expect(one(ended).error ?? null).toBeNull();
  });

  it("leaves an already settled pass alone at turn end", () => {
    const state = send(send(running(), open()), settle("completed"));
    const ended = reduce(state, {
      type: "run-end",
      status: { type: "complete", reason: "stop" },
    });
    expect(one(ended).status).toBe("completed");
    expect(one(ended).endedAt).toBe(one(state).endedAt);
  });

  it("drops an unknown id with no run and no replay to write into", () => {
    expect(send(EMPTY_ACP_THREAD_STATE, open())).toBe(EMPTY_ACP_THREAD_STATE);
    expect(send(EMPTY_ACP_THREAD_STATE, chunk("text"))).toBe(EMPTY_ACP_THREAD_STATE);
    const ended = reduce(send(running(), open("c1")), {
      type: "run-end",
      status: { type: "complete", reason: "stop" },
    });
    // A known id is patched wherever it lives; a new one has no live turn to
    // open in, so it is dropped rather than reopening a finished message.
    expect(send(ended, open("c2"))).toBe(ended);
  });

  it("writes into the replay assistant while a session is loading", () => {
    const replaying = reduce(EMPTY_ACP_THREAD_STATE, { type: "replay-start" });
    const state = send(replaying, open());
    expect(state.compactionMessages).toEqual({ c1: "acp-replay-0" });
    expect(one(state, "acp-replay-0").status).toBe("in_progress");
  });

  it("keeps the index past the turn so a late update finds its entity", () => {
    let state = send(running("a1"), open());
    state = reduce(state, { type: "run-end", status: { type: "complete", reason: "stop" } });
    state = reduce(state, { type: "run-start", message: assistant("a2") });
    state = send(state, settle("completed", { summary: [text("late")] }));
    // Patched where it lives, not reopened in the turn now running.
    expect(one(state, "a1").summary).toBe("late");
    expect(one(state, "a1").status).toBe("completed");
    expect(partsIn(state, "a2")).toHaveLength(0);
  });

  it("clears the index with the transcript", () => {
    const state = send(running(), open());
    const reset = reduce(state, { type: "reset-thread" });
    expect(reset.compactionMessages).toEqual({});
    expect(reset.messageOrder).toEqual([]);
    const replaced = reduce(state, {
      type: "replace-messages",
      messages: [],
      headId: null,
    });
    expect(replaced.compactionMessages).toEqual({});
  });
});

const at = (over: Partial<AcpCompaction> = {}): AcpCompaction => ({
  id: "c1",
  status: "completed",
  summary: "",
  startedAt: 0,
  endedAt: 3_200,
  ...over,
});

describe("compaction labels", () => {
  it("formats a duration the way the tool card does", () => {
    expect(formatDuration(0)).toBe("<1s");
    expect(formatDuration(-5)).toBe("<1s");
    expect(formatDuration(Number.NaN)).toBe("<1s");
    expect(formatDuration(999)).toBe("<1s");
    expect(formatDuration(1_000)).toBe("1.0s");
    expect(formatDuration(3_200)).toBe("3.2s");
    expect(formatDuration(60_000)).toBe("1m 0s");
    expect(formatDuration(125_000)).toBe("2m 5s");
  });

  it("counts and peeks the retained summary", () => {
    expect(summaryLines("")).toBe(0);
    expect(summaryLines("  \n\n")).toBe(0);
    expect(summaryLines("one")).toBe(1);
    expect(summaryLines("one\n\ntwo\n")).toBe(2);
    expect(firstSummaryLine("")).toBeUndefined();
    expect(firstSummaryLine("\n\n  kept the plan  \nsecond")).toBe("kept the plan");
  });

  it("ticks while open and freezes once settled", () => {
    const c = at({ status: "in_progress", endedAt: undefined, startedAt: 1_000 });
    expect(compactionElapsed(c, 4_200)).toBe(3_200);
    expect(compactionElapsed(at({ startedAt: 1_000, endedAt: 2_000 }), 99_000)).toBe(1_000);
    expect(compactionElapsed(at({ startedAt: 10_000 }), 1_000)).toBe(0);
  });

  it("says what the pass is doing while it runs", () => {
    const heading = compactionHeading(at({ status: "in_progress", endedAt: undefined }), 1_000);
    expect(heading).toEqual({ text: "Compacting context\u2026", tone: "active", open: true });
  });

  it("receipts a completed pass with its duration and the lines it kept", () => {
    expect(compactionHeading(at({ summary: "one\ntwo\n" }), 0).text).toBe(
      "Context compacted \u00b7 3.2s \u00b7 2 lines",
    );
    expect(compactionHeading(at({ summary: "one" }), 0).text).toBe(
      "Context compacted \u00b7 3.2s \u00b7 1 line",
    );
    // Nothing retained means nothing to count: quoting "0 lines" would be noise.
    expect(compactionHeading(at(), 0)).toEqual({
      text: "Context compacted \u00b7 3.2s",
      tone: "settled",
      open: false,
    });
  });

  it("receipts a failure with its reason", () => {
    expect(compactionHeading(at({ status: "failed", error: "boom" }), 0)).toEqual({
      text: "Compaction failed \u00b7 boom",
      tone: "failed",
      open: false,
    });
    expect(compactionHeading(at({ status: "failed" }), 0).text).toBe(
      "Compaction failed \u00b7 unknown",
    );
    expect(compactionHeading(at({ status: "failed", error: "" }), 0).text).toBe(
      "Compaction failed \u00b7 unknown",
    );
  });

  it("receipts a cancellation and an unknown status", () => {
    expect(compactionHeading(at({ status: "cancelled" }), 0)).toEqual({
      text: "Compaction cancelled \u00b7 3.2s",
      tone: "cancelled",
      open: false,
    });
    expect(compactionHeading(at({ status: "_crow_paused" }), 0)).toEqual({
      text: "Compaction _crow_paused \u00b7 3.2s",
      tone: "settled",
      open: false,
    });
  });
});
