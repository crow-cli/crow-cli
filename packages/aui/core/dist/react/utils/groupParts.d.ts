import type { PartState } from "../../store/scopes/part.js";
import type { ToolsState } from "../types/scopes/tools.js";
/**
 * Registry context passed to a `groupBy` function as its second argument by
 * `<MessagePrimitive.GroupedParts>`. Carries the live tool-UI registry so a
 * `groupBy` can resolve registry-driven grouping (e.g. standalone tool calls)
 * without the part itself having to carry that information.
 */
export type GroupByContext = {
    /** Tool UIs registered in the tool-UI registry, keyed by tool name. */
    readonly toolUIs?: ToolsState["toolUIs"];
};
/**
 * Hierarchical adjacent-coalescing grouping for message parts.
 *
 * Given a group path per part (from `groupBy`), builds a tree of group
 * nodes wrapping individual parts. Adjacent parts sharing a path prefix
 * coalesce into the same group; ungrouped parts are direct children of
 * the root.
 *
 * Each node gets a structural `nodeKey` built from sibling indices
 * (`"0.1.0"`), stable under append-only streaming.
 */
/**
 * Symbol attached to memoizable `groupBy` functions (e.g. those returned
 * by {@link groupPartByType}). Carries a string fingerprint of the config
 * so `MessagePrimitive.GroupedParts` can memo the tree on
 * `[parts, memoKey]` across renders — even when the helper call site
 * reconstructs the function each render.
 */
export declare const GROUPBY_MEMO_KEY: unique symbol;
/**
 * Synthetic part-type keys recognized by {@link groupPartByType}, in
 * addition to real {@link PartState} types:
 *
 * - `"standalone-tool-call"` — a tool-call whose UI should be presented on its
 *   own, outside the chain-of-thought grouping. Matches MCP-app tool calls plus
 *   any tool-call whose registered UI opts into standalone display (human
 *   tools, the built-in generative-UI tool, and tools that set
 *   `display: "standalone"`). Resolving the registry-driven cases reads the
 *   {@link GroupByContext} passed to the `groupBy` function. Takes precedence
 *   over the `"tool-call"` entry.
 *
 * A `"tool-call:<name>"` entry matches tool calls by tool name and takes precedence over the plain `"tool-call"` entry, while `"standalone-tool-call"` still wins first.
 */
type GroupPartType = PartState["type"] | "standalone-tool-call" | `tool-call:${string}`;
/**
 * Build a `groupBy` from a `part.type → group-key path` lookup.
 * Parts whose type isn't in the map are left ungrouped. The returned
 * function carries a stable {@link GROUPBY_MEMO_KEY} fingerprint so
 * `<MessagePrimitive.GroupedParts>` can memoize its tree across renders.
 *
 * The synthetic `"standalone-tool-call"` key matches tool calls that should
 * render outside the chain-of-thought grouping. MCP-app calls are detected from
 * the part alone; the registry-driven cases (human tools, the generative-UI
 * tool, `display: "standalone"` opt-ins) are resolved from the
 * {@link GroupByContext} that `<MessagePrimitive.GroupedParts>` passes to the
 * `groupBy` function — the helper needs nothing threaded into it.
 *
 * A `"tool-call:<name>"` entry matches tool calls by tool name and takes precedence over the plain `"tool-call"` entry, while `"standalone-tool-call"` still wins first.
 *
 * @example
 * ```tsx
 * <MessagePrimitive.GroupedParts
 *   groupBy={groupPartByType({
 *     reasoning: ["group-thought", "group-reasoning"],
 *     "tool-call:task": ["group-subagents"],
 *     "tool-call": ["group-thought", "group-tool"],
 *     "standalone-tool-call": [],
 *   })}
 * >
 *   {({ part, children }) => { ... }}
 * </MessagePrimitive.GroupedParts>
 * ```
 */
export declare const groupPartByType: <TKey extends `group-${string}`>(map: Partial<Readonly<Record<GroupPartType, readonly TKey[]>>>) => ((part: PartState, context?: GroupByContext) => readonly TKey[]);
export type GroupNode = GroupNodeGroup | GroupNodePart;
export interface GroupNodeGroup {
    readonly type: "group";
    /** Current-level group key (last segment of the path). */
    readonly key: string;
    /** Structural React key: sibling-index path, e.g. `"0.1.0"`. */
    readonly nodeKey: string;
    /**
     * Identity key (`"id:<type>:<partId>"`) from the group's first part; undefined when absent or already claimed by an earlier sibling.
     */
    readonly idKey: string | undefined;
    /** Indices of parts in this subtree, in order. */
    readonly indices: readonly number[];
    readonly children: readonly GroupNode[];
}
export interface GroupNodePart {
    readonly type: "part";
    /** Index of the part in the message. */
    readonly index: number;
    /** Structural React key: sibling-index path within parent. */
    readonly nodeKey: string;
    /**
     * Identity key (`"id:<partId>"`); undefined when absent or already
     * claimed by an earlier sibling.
     */
    readonly idKey: string | undefined;
}
/**
 * Build the group tree from an array of normalized group paths.
 * `paths[i]` is the path for part `i`. The output tree contains one
 * `part` node per part and one `group` node per coalesced run.
 */
export declare const buildGroupTree: (paths: readonly (readonly string[])[], partIds?: readonly (string | undefined)[]) => readonly GroupNode[];
export {};