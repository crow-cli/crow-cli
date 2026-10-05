import type { MessagePartStatus, ToolCallMessagePartStatus } from "../types/message.js";
type PartWithStatus = {
    readonly status: MessagePartStatus | ToolCallMessagePartStatus;
};
export declare const getGroupStatus: (parts: readonly (PartWithStatus | undefined)[]) => MessagePartStatus | ToolCallMessagePartStatus;
export declare const getGroupSummary: (parts: readonly (PartWithStatus | undefined)[], indices: readonly number[]) => {
    status: MessagePartStatus | {
        readonly type: "requires-action";
        readonly reason: "tool-calls" | "interrupt";
    } | {
        readonly type: "incomplete";
        readonly reason: "tool-calls";
        readonly error?: import("assistant-stream/utils").ReadonlyJSONValue;
    };
    counts: {
        running: number;
        complete: number;
        incomplete: number;
        requiresAction: number;
    };
};
export {};