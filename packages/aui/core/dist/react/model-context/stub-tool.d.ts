/**
 * Marks a generative toolkit entry as a frontend tool whose executor will be
 * supplied by `useAuiToolOverrides(...)`.
 *
 * `stubTool()` has no runtime implementation. It must be used inside a
 * `"use generative"` toolkit file so the compiler can strip it.
 */
export declare function stubTool(): never;