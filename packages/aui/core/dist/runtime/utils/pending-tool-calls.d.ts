type PendingToolCallMessage<TToolCall> = {
    toolCalls: readonly TToolCall[];
} | {
    toolCallId: string;
} | undefined;
export declare const scanPendingToolCalls: <TMessage, TToolCall>(messages: readonly TMessage[], getMessage: (message: TMessage) => PendingToolCallMessage<TToolCall>, getToolCallId: (toolCall: TToolCall) => string) => TToolCall[];
export declare const createToolCallCancellationStub: (toolCall: {
    readonly id: string;
    readonly name: string;
}) => {
    type: "tool";
    name: string;
    tool_call_id: string;
    content: string;
    status: "error";
};
export {};