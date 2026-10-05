/**
 * Hook that returns the elapsed wall-clock time of the current tool call in
 * milliseconds, ticking once per second while the call runs.
 *
 * Reads `part.timing`. Returns `undefined` when the part is not a tool call,
 * carries no timing, ended without a recorded completion (the duration is
 * unknown), or when no message part scope is available (so kit components
 * stay renderable standalone, e.g. in docs previews).
 *
 * @example
 * ```tsx
 * function ToolDuration() {
 *   const elapsedMs = useToolCallElapsed();
 *   if (elapsedMs === undefined) return null;
 *   return <span>{(elapsedMs / 1000).toFixed(1)}s</span>;
 * }
 * ```
 */
export declare const useToolCallElapsed: () => number | undefined;