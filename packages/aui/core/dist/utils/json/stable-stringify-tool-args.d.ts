import type { ReadonlyJSONObject } from "assistant-stream/utils";
export declare const trackToolArgsKeyOrder: (keyOrderCache: Map<string, Map<string, string[]>> | undefined, cacheKey: string, args: ReadonlyJSONObject) => void;
export declare const stableStringifyToolArgs: (keyOrderCache: Map<string, Map<string, string[]>> | undefined, cacheKey: string, args: ReadonlyJSONObject) => string;