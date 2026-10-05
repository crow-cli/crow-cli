import { type RefObject } from "react";
import type { ThreadHistoryAdapter } from "../../../adapters/thread-history.js";
import { type AssistantCloud, type RunMessageTelemetry } from "assistant-cloud";
import type { FeedbackAdapter } from "../../../adapters/feedback.js";
export declare function extractAuiV0<T>(content: T): RunMessageTelemetry | null;
export declare function useAssistantCloudThreadHistoryAdapter(cloudRef: RefObject<AssistantCloud>): ThreadHistoryAdapter & {
    readonly feedback: FeedbackAdapter;
};