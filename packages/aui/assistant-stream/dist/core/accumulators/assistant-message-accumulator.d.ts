import type { AssistantStreamChunk } from "../AssistantStreamChunk.js";
import type { AssistantMessage } from "../utils/types.js";
import type { ReadonlyJSONValue } from "../../utils.js";
export declare const createInitialMessage: ({ unstable_state, }?: {
    unstable_state?: ReadonlyJSONValue;
}) => AssistantMessage;
export declare class AssistantMessageAccumulator extends TransformStream<AssistantStreamChunk, AssistantMessage> {
    constructor({ initialMessage, throttle, onError, strict, }?: {
        initialMessage?: AssistantMessage;
        throttle?: boolean;
        onError?: (error: string) => void;
        strict?: boolean | undefined;
    });
}