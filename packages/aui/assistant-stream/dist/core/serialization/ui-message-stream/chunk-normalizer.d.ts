import type { UIMessageStreamChunk } from "./chunk-types.js";
export declare const createChunkNormalizer: () => {
    normalize(chunk: {
        type: string;
    } & Record<string, any>, controller: TransformStreamDefaultController<UIMessageStreamChunk>): void;
    flush(controller: TransformStreamDefaultController<UIMessageStreamChunk>): void;
};