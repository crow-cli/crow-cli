import type { AssistantStreamChunk } from "../../AssistantStreamChunk.js";
export declare const enqueueIfOpen: (controller: {
    enqueue(chunk: AssistantStreamChunk): void;
}, chunk: AssistantStreamChunk, onDrop?: (error: TypeError) => void) => void;
export declare const closeIfOpen: (controller: {
    close(): void;
}) => void;