import type { ThreadAssistantMessagePart, ThreadMessage, ToolCallMessagePart } from "../../types/message.js";
export type ToolCallTreeEntry = {
    readonly part: ToolCallMessagePart;
    /** Id of the message whose content directly holds `part`. */
    readonly messageId: string;
};
/**
 * Walk every tool-call part reachable from `messages`. A tool call projects a
 * child run as nested messages on `ToolCallMessagePart.messages`, so a
 * subagent's own calls live below the top-level content and a seam that only
 * scans the top level cannot reach them.
 *
 * Parts arrive in document order, each one ahead of its own descendants.
 * `messageId` names the message that directly holds the part, which for a
 * nested call is the child run's message rather than the top-level message the
 * tree hangs from. Only assistant messages are descended, the same rule
 * {@link mapToolCallPartsDeep} rewrites under, so a part this reports is always
 * a part that can be written back.
 */
export declare function walkToolCallTree(messages: readonly ThreadMessage[]): Generator<ToolCallTreeEntry>;
/**
 * Content-level form of {@link walkToolCallTree}, for a caller that already
 * holds one assistant message's content and does not need the owning id.
 */
export declare function iterateToolCallParts(content: readonly ThreadAssistantMessagePart[]): Generator<ToolCallMessagePart>;
/**
 * Rebuild `content` with `fn` applied to every tool-call part in the tree.
 * Arrays and nested messages are reused wherever `fn` returned the part it was
 * given, so an unchanged subtree keeps its identity and `changed` reports
 * whether anything moved.
 */
export declare function mapToolCallPartsDeep(content: readonly ThreadAssistantMessagePart[], fn: (part: ToolCallMessagePart) => ToolCallMessagePart): {
    content: readonly ThreadAssistantMessagePart[];
    changed: boolean;
};