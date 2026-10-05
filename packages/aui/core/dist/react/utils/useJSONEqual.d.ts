import type { ReadonlyJSONValue } from "assistant-stream/utils";
export declare function useJSONEqualValue<T extends ReadonlyJSONValue>(value: T): T;
/**
 * Like `useShallow`, but with JSON deep-equality. Use when a selector derives an
 * equal-but-fresh value on every store update — e.g. folding over
 * `thread.messages`, whose identity changes on every streaming token — where a
 * shallow compare would re-render regardless.
 */
export declare function useJSONEqual<S, U>(selector: (state: S) => U): (state: S) => U;