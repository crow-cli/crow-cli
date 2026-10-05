import type { ReadonlyJSONValue } from "../../utils.js";
import type { GorpStreamOperation } from "./types.js";
export declare class GorpStreamDeltaTracker {
    private readonly accumulator;
    private previousState;
    private changes;
    constructor(initialValue?: ReadonlyJSONValue);
    get state(): ReadonlyJSONValue;
    append(operations: readonly GorpStreamOperation[]): void;
    isChangedAt(path: readonly string[]): boolean;
    getChangedKeys(path: readonly string[]): string[];
}