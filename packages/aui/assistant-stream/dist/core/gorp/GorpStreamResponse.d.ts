import { PipeableTransformStream } from "../utils/stream/PipeableTransformStream.js";
import type { GorpStreamChunk } from "./types.js";
export declare class GorpStreamEncoder extends PipeableTransformStream<GorpStreamChunk, Uint8Array> {
    constructor();
}
export declare class GorpStreamDecoder extends PipeableTransformStream<Uint8Array<ArrayBuffer>, GorpStreamChunk> {
    constructor();
}
export declare class GorpStreamResponse extends Response {
    constructor(body: ReadableStream<GorpStreamChunk>);
}
export declare const fromGorpStreamResponse: (response: Response) => ReadableStream<GorpStreamChunk>;