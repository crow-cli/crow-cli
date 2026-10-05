import type { ReadonlyJSONValue } from "../../utils.js";
import type { GorpStreamOperation } from "./types.js";
export declare class GorpStreamAccumulator {
    private _state;
    private readonly _strict;
    private readonly _logged;
    private _warnedClamp;
    constructor(initialValue?: ReadonlyJSONValue, options?: {
        strict?: boolean;
    });
    get state(): ReadonlyJSONValue;
    private logOnce;
    append(ops: readonly GorpStreamOperation[]): void;
    private apply;
    private updatePath;
}