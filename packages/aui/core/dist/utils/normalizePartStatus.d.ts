import type { MessagePartStatus, ThreadAssistantMessagePart, ThreadMessage, ThreadUserMessagePart, ToolCallMessagePart, ToolCallMessagePartStatus } from "../types/message.js";
export declare const COMPLETE_STATUS: MessagePartStatus;
export declare const RUNNING_STATUS: MessagePartStatus;
export declare const normalizePartStatus: (part: ThreadUserMessagePart | ThreadAssistantMessagePart) => MessagePartStatus | undefined;
export declare const hasPendingToolAction: (part: Pick<ToolCallMessagePart, "approval" | "interrupt">) => boolean;
export declare const toMessagePartStatus: (message: ThreadMessage, partIndex: number, part: ThreadUserMessagePart | ThreadAssistantMessagePart) => ToolCallMessagePartStatus;