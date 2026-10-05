export type Unstable_MessageStallDetectionOptions = {
    /**
     * Milliseconds of unchanged message content before the message counts as
     * stalled.
     * @default 2000
     */
    thresholdMs?: number | undefined;
};
export type Unstable_MessageStallDetection = {
    /** True while the message is running and its content has not changed for at least `thresholdMs`. */
    stalled: boolean;
    /** Milliseconds since the last observed content change. `0` while not stalled. */
    stalledForMs: number;
};
/**
 * @deprecated Under active development and might change without notice.
 *
 * Detects mid-run output stalls on the current message: while the message is
 * running, watches its text, reasoning, and tool-argument values plus tool-result
 * availability and reports a stall once they stop changing for `thresholdMs`.
 * Useful for re-surfacing a "still working" indicator during tool think-time or
 * provider stalls, after the first tokens have already streamed.
 *
 * Must be used inside a message scope.
 */
export declare function unstable_useMessageStallDetection(options?: Unstable_MessageStallDetectionOptions): Unstable_MessageStallDetection;