import type { AssistantStreamEncoder } from "../AssistantStream.js";
import type { AssistantStreamChunk } from "../AssistantStreamChunk.js";
import { PipeableTransformStream } from "../utils/stream/PipeableTransformStream.js";
export declare class PlainTextEncoder extends PipeableTransformStream<AssistantStreamChunk, Uint8Array<ArrayBuffer>> implements AssistantStreamEncoder {
    headers: Headers;
    constructor();
}
export declare class PlainTextDecoder extends PipeableTransformStream<Uint8Array<ArrayBuffer>, AssistantStreamChunk> {
    constructor();
}