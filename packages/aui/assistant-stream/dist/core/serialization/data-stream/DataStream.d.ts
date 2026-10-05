import type { AssistantStreamChunk } from "../../AssistantStreamChunk.js";
import { PipeableTransformStream } from "../../utils/stream/PipeableTransformStream.js";
import type { AssistantStreamEncoder } from "../../AssistantStream.js";
type DataStreamOptions = {
    strict?: boolean | undefined;
};
export declare class DataStreamEncoder extends PipeableTransformStream<AssistantStreamChunk, Uint8Array<ArrayBuffer>> implements AssistantStreamEncoder {
    headers: Headers;
    constructor();
}
export declare class DataStreamDecoder extends PipeableTransformStream<Uint8Array<ArrayBuffer>, AssistantStreamChunk> {
    constructor(options?: DataStreamOptions);
}
export {};