import type {
  DataMessagePart,
  ThreadAssistantMessage,
} from "@assistant-ui/core";
import type {
  AcpCompaction,
  AcpCompactionStatus,
  AcpContentBlock,
} from "./types";

type AssistantPart = ThreadAssistantMessage["content"][number];

/**
 * Context compaction, client side.
 *
 * The wire gives a client two notifications and no capability handshake:
 * `compaction_update` upserts the entity a `compactionId` names, and
 * `compaction_summary_chunk` appends one content block to its retained
 * summary while it is open. Together they are the only explanation a client
 * has for a context meter that just fell — without them the used/size reading
 * drops with nothing to say why.
 *
 * crow-client renders this as a transcript cell (`CellKind::Compaction`),
 * upserted by id so the first update fixes its position in the timeline and
 * every later one patches it in place. A thread here has no cell list, so the
 * entity rides the assistant message's content as a named `data` part with the
 * compaction id as its part id: the position is where the first update landed,
 * the id keeps the render key stable across every patch, and a host draws it
 * by registering a data renderer under {@link ACP_COMPACTION_PART}.
 */

/** The `data` part name a compaction is projected into. */
export const ACP_COMPACTION_PART = "acp-compaction";

export type AcpCompactionPart = DataMessagePart<AcpCompaction> & {
  readonly name: typeof ACP_COMPACTION_PART;
};

export const isCompactionPart = (
  part: AssistantPart,
): part is AcpCompactionPart =>
  part.type === "data" && part.name === ACP_COMPACTION_PART;

/**
 * True only while the compaction has not reached a terminal state. An
 * unrecognized status counts as SETTLED: the schema reserves `_`-prefixed
 * values for implementations and the rest for future ACP statuses, so this is
 * expected to happen, and treating an unknown status as open would leave the
 * card spinning forever.
 */
export const isCompactionOpen = (status: AcpCompactionStatus): boolean =>
  status === "in_progress";

/**
 * The `.text` of every `type: "text"` block, concatenated — crow-client's
 * `concat_text_blocks`. `null` and `[]` both read as "", which is the explicit
 * clear the schema means by them.
 */
export const compactionSummaryText = (
  blocks: readonly AcpContentBlock[] | null | undefined,
): string => {
  if (!blocks) return "";
  let out = "";
  for (const block of blocks) {
    if (block.type === "text" && typeof block.text === "string") {
      out += block.text;
    }
  }
  return out;
};

/**
 * What one `compaction_update` changes. An absent field keeps the retained
 * value — the schema's patch semantics, where omission and `null` are
 * different acts. `summary` is already flattened to text, so `undefined` means
 * "keep what streamed" and `""` means "clear it".
 */
export type AcpCompactionPatch = {
  readonly status?: AcpCompactionStatus | undefined;
  readonly summary?: string | undefined;
  readonly error?: string | null | undefined;
};

/**
 * One entity plus one patch. Returns the entity itself when the patch changes
 * nothing, so a caller can skip the copy that would otherwise re-render a card
 * on every duplicate update an agent replays.
 */
const applyPatch = (
  compaction: AcpCompaction,
  patch: AcpCompactionPatch,
  now: number,
): AcpCompaction => {
  const status = patch.status ?? compaction.status;
  const summary = patch.summary ?? compaction.summary;
  const error = patch.error === undefined ? compaction.error : patch.error;
  // The duration freezes the moment the pass settles, and only then: a
  // terminal patch over an already-settled entity must not move it.
  const endedAt =
    !isCompactionOpen(status) && compaction.endedAt == null
      ? now
      : compaction.endedAt;
  if (
    status === compaction.status &&
    summary === compaction.summary &&
    error === compaction.error &&
    endedAt === compaction.endedAt
  ) {
    return compaction;
  }
  return {
    ...compaction,
    status,
    summary,
    ...(error != null ? { error } : { error: null }),
    ...(endedAt != null && { endedAt }),
  };
};

const partFor = (compaction: AcpCompaction): AcpCompactionPart => ({
  type: "data",
  id: compaction.id,
  name: ACP_COMPACTION_PART,
  data: compaction,
});

const replaceAt = (
  content: readonly AssistantPart[],
  index: number,
  part: AssistantPart,
): readonly AssistantPart[] => [
  ...content.slice(0, index),
  part,
  ...content.slice(index + 1),
];

const indexOfCompaction = (
  content: readonly AssistantPart[],
  id: string,
): number => {
  for (let i = 0; i < content.length; i++) {
    const part = content[i]!;
    if (isCompactionPart(part) && part.id === id) return i;
  }
  return -1;
};

/** The part a first sight of an id mints, positioned by whoever appends it. */
export const newCompactionPart = (
  id: string,
  patch: AcpCompactionPatch,
  now: number,
): AcpCompactionPart => {
  const status = patch.status ?? "in_progress";
  return partFor({
    id,
    status,
    summary: patch.summary ?? "",
    ...(patch.error !== undefined && { error: patch.error }),
    startedAt: now,
    // An entity whose first update is already terminal was replayed, not
    // watched: there is no duration to report, so it settles at zero.
    ...(!isCompactionOpen(status) && { endedAt: now }),
  });
};

/**
 * Patch the part carrying `id`. Returns `undefined` when the message holds no
 * such part or the patch would change nothing, so a caller can tell "no new
 * content" from "new content" without comparing arrays.
 */
export const applyCompactionPatch = (
  content: readonly AssistantPart[],
  id: string,
  patch: AcpCompactionPatch,
  now: number,
): readonly AssistantPart[] | undefined => {
  const index = indexOfCompaction(content, id);
  if (index < 0) return undefined;
  const part = content[index] as AcpCompactionPart;
  const next = applyPatch(part.data, patch, now);
  return next === part.data ? undefined : replaceAt(content, index, partFor(next));
};

/**
 * Append one streamed chunk to the retained summary. A chunk whose id has no
 * part yet is out of spec — the agent owes an `in_progress` update first — and
 * the caller decides whether to mint the entity late rather than drop the text.
 */
export const appendCompactionSummary = (
  content: readonly AssistantPart[],
  id: string,
  text: string,
): readonly AssistantPart[] | undefined => {
  if (!text) return undefined;
  const index = indexOfCompaction(content, id);
  if (index < 0) return undefined;
  const part = content[index] as AcpCompactionPart;
  return replaceAt(content, index, {
    ...part,
    data: { ...part.data, summary: part.data.summary + text },
  });
};

/**
 * Settle every compaction in `content` that is still open. A turn that ends
 * with a pass in flight means the agent or the connection died mid-compaction
 * — agent2 always reports its own terminal status, `cancelled` included,
 * because `asyncio.CancelledError` is a `BaseException` that `except Exception`
 * sails past. Left open, the card spins forever on a turn that is over.
 */
export const settleOpenCompactions = (
  content: readonly AssistantPart[],
  status: AcpCompactionStatus,
  error: string | null,
  now: number,
): readonly AssistantPart[] | undefined => {
  let next: readonly AssistantPart[] | undefined;
  for (let i = 0; i < content.length; i++) {
    const part = content[i]!;
    if (!isCompactionPart(part) || !isCompactionOpen(part.data.status)) {
      continue;
    }
    const settled = applyPatch(
      part.data,
      { status, ...(error !== null && { error }) },
      now,
    );
    const replaced = replaceAt(next ?? content, i, partFor(settled));
    next = replaced;
  }
  return next;
};
