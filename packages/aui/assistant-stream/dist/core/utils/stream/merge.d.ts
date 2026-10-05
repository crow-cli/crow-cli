import type { AssistantStreamChunk } from "../../AssistantStreamChunk.js";
export declare const createMergeStream: () => {
    readable: ReadableStream<AssistantStreamChunk>;
    isSealed(): boolean;
    isCancelled(): boolean;
    isErrored(): boolean;
    seal(): void;
    addStream: (stream: ReadableStream<AssistantStreamChunk>, pipeTask?: Promise<unknown>) => void;
    enqueue(chunk: AssistantStreamChunk): void;
};