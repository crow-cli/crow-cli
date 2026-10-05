import type { ReadonlyJSONValue } from "../../utils.js";
import type { GorpStreamOperation, GorpStreamChunk } from "./types.js";
type GorpStreamController = {
    readonly abortSignal: AbortSignal;
    enqueue(operations: readonly GorpStreamOperation[]): void;
};
type CreateGorpStreamOptions = {
    execute: (controller: GorpStreamController) => void | PromiseLike<void>;
    defaultValue?: ReadonlyJSONValue;
};
export declare const createGorpStream: ({ execute, defaultValue, }: CreateGorpStreamOptions) => ReadableStream<GorpStreamChunk>;
export {};