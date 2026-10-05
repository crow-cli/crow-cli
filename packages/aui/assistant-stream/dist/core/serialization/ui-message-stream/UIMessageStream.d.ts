import type { AssistantStreamChunk } from "../../AssistantStreamChunk.js";
import { PipeableTransformStream } from "../../utils/stream/PipeableTransformStream.js";
import type { UIMessageStreamChunk, UIMessageStreamDataChunk } from "./chunk-types.js";
export type { UIMessageStreamChunk, UIMessageStreamDataChunk };
export type UIMessageStreamDecoderOptions = {
    onData?: (data: {
        type: string;
        name: string;
        data: unknown;
        transient?: boolean;
    }) => void;
};
/**
 * Decodes AI SDK v6 UI Message Stream format into AssistantStreamChunks.
 */
export declare class UIMessageStreamDecoder extends PipeableTransformStream<Uint8Array<ArrayBuffer>, AssistantStreamChunk> {
    constructor(options?: UIMessageStreamDecoderOptions);
}