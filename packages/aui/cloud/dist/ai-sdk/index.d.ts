import type { UIMessage } from "ai";
import type { MessageFormatAdapter } from "../FormattedCloudPersistence.js";
import { type RunMessageTelemetry } from "../runTelemetry.js";
export type AISDKStorageFormat = Omit<UIMessage, "id">;
/** The stored form of an AI SDK message: the message without its id. */
export declare const aiSDKV6FormatAdapter: MessageFormatAdapter<UIMessage, AISDKStorageFormat>;
/**
 * A message as an AI SDK integration holds it, or as the cloud stored it under
 * the ai-sdk/v6 format, which drops the id. Parts are typed by their `type`
 * alone, so this shape and the telemetry read from it need nothing from `ai`.
 */
export type AISDKMessageLike = {
    id?: string | undefined;
    role: string;
    parts: readonly {
        type: string;
        [key: string]: unknown;
    }[];
    metadata?: unknown;
};
/**
 * Reads the run report fields out of the assistant messages of one run. A run
 * the AI SDK streamed as one message is one element; a run the cloud stored as
 * several assistant rows is aggregated, step by step, in order. Returns null
 * when no assistant message is present. Status reads completed when the run
 * produced text or tool calls, as a live finish with reason `tool-calls` does;
 * an integration that observed the finish event overrides it.
 */
export declare function extractAISDKRunTelemetry(messages: readonly AISDKMessageLike[]): RunMessageTelemetry | null;