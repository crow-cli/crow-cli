import type { DataStreamChunk } from "./chunk-types.js";
export declare class DataStreamChunkEncoder extends TransformStream<DataStreamChunk, string> {
    constructor();
}
export declare class DataStreamChunkDecoder extends TransformStream<string, DataStreamChunk> {
    constructor();
}