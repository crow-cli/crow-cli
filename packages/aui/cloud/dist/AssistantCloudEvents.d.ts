import type { AssistantCloudAPI } from "./AssistantCloudAPI.js";
export type AssistantCloudEventKind = "message_sent" | "message_edited" | "run_stopped" | "message_regenerated" | "message_copied" | "branch_switched" | "suggestions_shown" | "suggestion_clicked" | "attachment_added" | "attachment_failed" | "thread_switched" | "tool_approved" | "tool_rejected" | "speech_started" | "voice_started" | "error_shown";
export type AssistantCloudEvent = {
    kind: AssistantCloudEventKind;
    thread_id?: string | undefined;
    message_id?: string | undefined;
    run_id?: string | undefined;
    value?: number | undefined;
    props?: Readonly<Record<string, string | number | boolean>> | undefined;
};
export declare const clearPendingAssistantCloudEvents: (events: AssistantCloudEvents) => void;
export declare class AssistantCloudEvents {
    private buffer;
    private timer;
    private flushing;
    private retryTimer;
    private resolveRetryDelay;
    private bestEffortRequested;
    private generation;
    private readonly cloud;
    private readonly isEnabled;
    private listening;
    constructor(cloud: AssistantCloudAPI, isEnabled: () => boolean);
    track(event: AssistantCloudEvent): void;
    private listen;
    private unlisten;
    dispose(): void;
    private clearPending;
    private onVisibilityChange;
    private flushBestEffort;
    private flush;
    private flushPending;
    private waitForRetry;
    private interruptRetryDelay;
    private scheduleFlush;
    private clearFlushTimer;
}