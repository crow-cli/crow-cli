import { type TriggerMatch, type TriggerMatcher } from "./detectTrigger.js";
/** Detected trigger position within the composer text. */
export type DetectedTrigger = TriggerMatch;
export type TriggerDetectionResourceOutput = {
    /** Detected trigger (or `null` when inactive). */
    readonly trigger: DetectedTrigger | null;
    /** Current query string (empty when no trigger active). */
    readonly query: string;
    /** Update the tracked cursor position (wired to composer input). */
    setCursorPosition(pos: number): void;
};
export declare const TriggerDetectionResource: import("@assistant-ui/tap").Resource<TriggerDetectionResourceOutput, [{
    text: string;
    triggerChar: string;
    matcher?: TriggerMatcher | undefined;
}]>;