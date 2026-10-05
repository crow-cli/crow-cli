import type { AssistantStream } from "../AssistantStream.js";
import type { AssistantStreamChunk } from "../AssistantStreamChunk.js";
import type { UnderlyingReadable } from "../utils/stream/UnderlyingReadable.js";
export type TextStreamController = {
    append(textDelta: string): void;
    close(): void;
};
type TextStreamOptions = {
    strict?: boolean | undefined;
};
export declare const createTextStream: (readable: UnderlyingReadable<TextStreamController>, options?: TextStreamOptions) => AssistantStream;
export declare const createTextStreamController: (options?: TextStreamOptions) => readonly [ReadableStream<AssistantStreamChunk>, TextStreamController];
export {};