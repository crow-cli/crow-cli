import type { Resource } from "./types.js";
export declare function resource<R, A extends readonly unknown[]>(hook: (...args: A) => R): Resource<R, A>;