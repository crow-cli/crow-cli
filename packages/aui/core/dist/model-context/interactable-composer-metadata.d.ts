/**
 * Unstable / Experimental — the interactables API is still evolving and may change in any release.
 * @deprecated Unstable / Experimental (not actually removed).
 */
export type Unstable_InteractableSnapshotEntry = {
    id: string;
    name: string;
    state: unknown;
    /**
     * When true, `state` carries only the top-level fields that changed since
     * the model's last known state; omitted fields are unchanged. The first
     * snapshot of an instance is always full.
     */
    partial?: boolean | undefined;
};
/**
 * Minimal message shape needed to read snapshots and `update_*` tool calls out
 * of history. Structurally compatible with both `ThreadMessage` and the AI
 * SDK's `UIMessage`.
 */
type SnapshotCarrierMessage = {
    role: string;
    metadata?: unknown;
    content?: readonly unknown[] | undefined;
};
/**
 * Reads the interactable snapshots stamped on a message's
 * `metadata.custom.interactables`, or `undefined` if none. This is the read
 * half of the snapshot channel — integrations use it to surface interactable
 * state to the model (see `unstable_injectInteractableContext` in
 * `@assistant-ui/ai-sdk` for the AI SDK implementation).
 *
 * @deprecated Unstable / Experimental (not actually removed).
 */
export declare function unstable_getInteractableSnapshots(message: {
    metadata?: unknown;
}): Unstable_InteractableSnapshotEntry[] | undefined;
/**
 * Canonical model-facing wording for one snapshot entry.
 *
 * @deprecated Unstable / Experimental (not actually removed).
 */
export declare function unstable_formatInteractableSnapshot(entry: Unstable_InteractableSnapshotEntry): string;
/** The model-facing tool name for an interactable `name`. One tool per name. */
export declare function interactableToolName(name: string): string;
/**
 * Overlays a streamed `value` onto `prev` along the parser's `partialPath`:
 * the record still being written keeps the fields of `prev` it has not
 * reached yet, while every field the parser has closed replaces its previous
 * value, as the final merge will.
 */
export declare function overlayPartialPath(prev: unknown, value: unknown, partialPath?: readonly string[]): unknown;
/**
 * The merge `update_*` tools apply: top-level keys replace, rest preserved.
 * Array fields also accept operation objects (`add`, `update`, `remove`,
 * `clear`, `set`) so collection edits do not need a companion manage_* tool.
 */
export declare function shallowMergeInteractableState(prev: unknown, partial: unknown, options?: {
    arrayBaseline?: unknown;
    /**
     * Supplies ids for added items in id-keyed array fields. The live
     * execute path mints fresh ids; history folds replay ids previously
     * returned by execute.
     */
    idFactory?: (field: string) => string | undefined;
    idKeyedFields?: ReadonlySet<string>;
    /**
     * The path of the value the argument parser reports as still
     * streaming. The record there is overlaid onto its previous value
     * so its unwritten fields hold until the model writes them; omitted
     * once the arguments are complete.
     */
    partialPath?: readonly string[] | undefined;
} | undefined): unknown;
/**
 * Unstable / Experimental — the interactables API is still evolving and may change in any release.
 * @deprecated Unstable / Experimental (not actually removed).
 */
export type Unstable_InteractableVersion = {
    /** The full state as of this version. */
    state: unknown;
    origin: "create" | "update" | "user-edit";
    /** For create/update versions, the tool call that produced this version. */
    toolCallId?: string | undefined;
};
/**
 * Every version of interactable `id` recorded in the thread, oldest first,
 * folded chronologically:
 *
 * - the tool call whose `toolCallId` equals `id` seeds the baseline with its
 *   args (`origin: "create"`) — the `id: toolCallId` convention for
 *   tool-created interactables,
 * - a snapshot stamped on a user message is a `"user-edit"` version (a full
 *   snapshot replaces the state; a partial one shallow-merges),
 * - each accepted `update_*` call shallow-merges an `"update"` version.
 *
 * The last entry is the state the model knows. Partial snapshots and update
 * calls with no baseline to merge into are skipped.
 *
 * @deprecated Unstable / Experimental (not actually removed).
 */
export declare function unstable_getInteractableVersions(messages: readonly SnapshotCarrierMessage[], id: string, name: string): Unstable_InteractableVersion[];
/**
 * The state the model knows for interactable `id` — its latest recorded
 * version, or `undefined` when no baseline exists yet.
 */
export declare function findModelKnownState(messages: readonly SnapshotCarrierMessage[], id: string, name: string): {
    state: unknown;
} | undefined;
/**
 * Snapshot gate. Stamps an interactable only when the model doesn't already
 * know its state (no baseline yet, or the live state differs from the folded
 * thread record). A change that fits a shallow merge is stamped as a partial
 * snapshot carrying just the changed fields; otherwise the full state is
 * stamped. Other metadata keys pass through untouched.
 */
export declare function gateInteractableComposerMetadata(meta: Record<string, unknown> | undefined, messages: readonly SnapshotCarrierMessage[]): Record<string, unknown> | undefined;
export {};