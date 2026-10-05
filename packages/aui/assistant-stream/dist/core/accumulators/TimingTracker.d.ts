import type { AssistantMessageTiming } from "../utils/types.js";
export declare class TimingTracker {
    private _streamStartTime;
    private _firstTokenTime;
    private _totalChunks;
    private _toolCallIds;
    constructor();
    recordChunk(): void;
    recordFirstToken(): void;
    recordToolCallStart(toolCallId: string): void;
    getTiming(outputTokens?: number, totalText?: string): AssistantMessageTiming;
}