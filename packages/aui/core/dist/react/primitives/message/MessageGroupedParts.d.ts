import { type ReactNode } from "react";
import type { PartState } from "../../../store/scopes/part.js";
import type { MessagePartStatus, ToolCallMessagePartStatus } from "../../../types/message.js";
import { type GroupByContext } from "../../utils/groupParts.js";
import { type EnrichedPartState } from "./MessageParts.js";
export declare namespace MessagePrimitiveGroupedParts {
    /** Per status tallies over the group's `indices`; they sum to `indices.length`. */
    type GroupCounts = {
        readonly running: number;
        readonly complete: number;
        readonly incomplete: number;
        readonly requiresAction: number;
    };
    /**
     * A coalesced group of adjacent parts. Surfaced through the same
     * `{ part }` channel as a leaf {@link EnrichedPartState} so consumers
     * dispatch on a single `switch (part.type)`. `type` is the group key
     * (always `"group-…"`); `status` is running when any contained part runs,
     * otherwise it mirrors the last contained part.
     */
    type GroupPart<TKey extends `group-${string}` = `group-${string}`> = {
        readonly type: TKey;
        readonly status: MessagePartStatus | ToolCallMessagePartStatus;
        /** Per status tallies over `indices`. */
        readonly counts: GroupCounts;
        readonly indices: readonly number[];
    };
    /**
     * Synthetic trailing slot for a streaming/loading affordance (a
     * "thinking…" dot, etc.). Surfaced through the same `{ part }` channel
     * as groups and leaf parts so a single `switch (part.type)` renders it
     * via `case "indicator"`.
     *
     * It is only ever emitted while the message is running, so its presence
     * alone means "render your loading UI here" — there's no `status` to
     * branch on.
     */
    type IndicatorPart = {
        readonly type: "indicator";
    };
    /**
     * When to emit the synthetic {@link IndicatorPart}. It is **only** emitted
     * while the message is running (streaming); the mode further restricts
     * which running states qualify:
     * - `"never"` — never.
     * - `"empty"` — only when the message has no parts yet.
     * - `"no-text"` (default) — when the message has no parts yet or the last
     *   part isn't `text`/`reasoning` (e.g. it ended on a tool call, so the
     *   assistant likely isn't done).
     * - `"always"` — whenever the message is running, regardless of parts.
     */
    type IndicatorMode = "never" | "empty" | "no-text" | "always";
    type RenderInfo<TKey extends `group-${string}` = `group-${string}`> = {
        /**
         * Either a coalesced group ({@link GroupPart}, identified by a
         * `group-…` `type`), a single enriched leaf part, or the synthetic
         * {@link IndicatorPart} (`type: "indicator"`). Use one switch over
         * `part.type` to handle all three.
         */
        readonly part: GroupPart<TKey> | EnrichedPartState | IndicatorPart;
        /**
         * For group nodes: the recursively-rendered subtree (subgroups +
         * leaf parts). For leaf parts: a sentinel that throws when rendered
         * — accidental fall-through (`default: return children;`) errors
         * loudly instead of silently rendering nothing. Returning `null` for a
         * leaf renders its registered tool or data UI, when one exists; return an
         * empty fragment to suppress that registered UI explicitly.
         */
        readonly children: ReactNode;
    };
    type Props<TKey extends `group-${string}` = `group-${string}`> = {
        /**
         * Maps each part to a group-key path. Adjacent parts that share a
         * prefix coalesce into the same group. Return `[]` (or `null`) to
         * leave a part ungrouped.
         *
         * Group keys must start with `"group-"` so the renderer's
         * `switch (part.type)` can tell groups apart from real part types.
         *
         * **Prefer {@link groupPartByType}** for the common case of mapping by
         * `part.type` or tool name — it ships a stable memo fingerprint so the tree
         * survives unrelated re-renders. Use an inline function only when
         * the helper isn't expressive enough (e.g. branching on
         * `part.parentId` or part metadata).
         *
         * The second argument is a {@link GroupByContext} carrying the tool-UI
         * registry, for grouping that depends on it (e.g. standalone tool calls).
         *
         * @example
         * ```tsx
         * import { groupPartByType } from "@assistant-ui/react";
         *
         * <MessagePrimitive.GroupedParts
         *   groupBy={groupPartByType({
         *     reasoning: ["group-thought", "group-reasoning"],
         *     "tool-call": ["group-thought", "group-tool"],
         *   })}
         * >
         * ```
         */
        readonly groupBy: (part: PartState, context: GroupByContext) => readonly TKey[] | null;
        /**
         * Controls emission of the synthetic {@link IndicatorPart} — a
         * trailing `{ part: { type: "indicator", status } }` render call you
         * handle with `case "indicator"` to show loading/status UI.
         *
         * @default "no-text"
         * @see IndicatorMode
         */
        readonly indicator?: IndicatorMode;
        /**
         * Render function called once per group node, once per leaf part, and
         * (when the `indicator` condition is met) once for the trailing
         * {@link IndicatorPart}. Switch on `part.type`: `"group-…"` cases wrap
         * `children`; real part types (`"text"`, `"tool-call"`, …) render the
         * part directly. Returning `null` for a tool or data leaf uses its
         * registered UI, while an empty fragment suppresses it; `"indicator"`
         * renders status/loading UI.
         *
         * Leaf parts receive the same {@link EnrichedPartState} that
         * `<MessagePrimitive.Parts>` would produce (`toolUI`, `addResult`,
         * `resume`, `respondToApproval`, `unstable_recordInteraction`,
         * `dataRendererUI`).
         */
        readonly children: (info: RenderInfo<TKey>) => ReactNode;
    };
}
/**
 * Groups adjacent message parts into a tree of coalesced runs and
 * renders each node — group or part — through a single `children`
 * function.
 *
 * The render function receives `{ part, children }` where `part.type`
 * is either a `"group-…"` literal (for a group, `children` is the
 * recursively-rendered subtree) or a real part type (`"text"`,
 * `"tool-call"`, …) for a leaf (`children` is a sentinel that throws
 * if rendered — use `part.type` to distinguish).
 *
 * @example
 * ```tsx
 * <MessagePrimitive.GroupedParts
 *   groupBy={groupPartByType({
 *     reasoning: ["group-thought", "group-reasoning"],
 *     "tool-call": ["group-thought", "group-tool"],
 *   })}
 * >
 *   {({ part, children }) => {
 *     switch (part.type) {
 *       case "group-thought":   return <Thought>{children}</Thought>;
 *       case "group-reasoning": return <Reasoning>{children}</Reasoning>;
 *       case "group-tool":      return <ToolStack>{children}</ToolStack>;
 *       case "text":            return <MarkdownText />;
 *       case "tool-call":       return part.toolUI ?? <ToolFallback {...part} />;
 *       case "indicator":       return <LoadingDots />;
 *       default:                return null;
 *     }
 *   }}
 * </MessagePrimitive.GroupedParts>
 * ```
 */
export declare const MessagePrimitiveGroupedParts: {
    <TKey extends `group-${string}`>({ groupBy, indicator, children, }: MessagePrimitiveGroupedParts.Props<TKey>): ReactNode;
    displayName: string;
};