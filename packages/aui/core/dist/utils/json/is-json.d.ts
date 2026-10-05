import type { ReadonlyJSONArray, ReadonlyJSONObject, ReadonlyJSONValue } from "assistant-stream/utils";
export declare function isRecord(value: unknown): value is Record<string, unknown>;
export declare function isJSONValue(value: unknown, currentDepth?: number): value is ReadonlyJSONValue;
export declare function isJSONArray(value: unknown): value is ReadonlyJSONArray;
export declare function isJSONObject(value: unknown): value is ReadonlyJSONObject;