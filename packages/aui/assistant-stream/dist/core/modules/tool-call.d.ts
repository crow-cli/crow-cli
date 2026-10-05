import type { AssistantStream } from "../AssistantStream.js";
import type { AssistantStreamChunk } from "../AssistantStreamChunk.js";
import { type ToolResponseLike } from "../tool/ToolResponse.js";
import type { ReadonlyJSONValue } from "../../utils/json/json-value.js";
import type { UnderlyingReadable } from "../utils/stream/UnderlyingReadable.js";
import { type TextStreamController } from "./text.js";
export type ToolCallStreamController = {
    argsText: TextStreamController;
    /**
     * Sets a tool response. Preliminary responses keep the part open; a final
     * response closes it automatically and subsequent calls are ignored.
     */
    setResponse(response: ToolResponseLike<ReadonlyJSONValue>): void;
    close(): void;
};
type ToolCallStreamOptions = {
    strict?: boolean | undefined;
};
export declare const createToolCallStream: (readable: UnderlyingReadable<ToolCallStreamController>, options?: ToolCallStreamOptions) => AssistantStream;
export declare const createToolCallStreamController: (options?: ToolCallStreamOptions) => readonly [ReadableStream<AssistantStreamChunk>, ToolCallStreamController];
export {};