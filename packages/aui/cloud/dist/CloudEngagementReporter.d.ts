import type { AssistantCloud } from "./AssistantCloud.js";
import type { AssistantCloudEvent } from "./AssistantCloudEvents.js";
export type EngagementEventIds = Pick<AssistantCloudEvent, "thread_id" | "message_id" | "run_id">;
/**
 * Turns the ids an integration knows (its own thread and message ids) into the
 * ids the cloud stores. A send is the one event that may create the remote
 * thread, so it asks for `awaitThread`; every other event reads the ids that
 * already exist. Returning nothing declines the event: the thread is not one
 * the integration knows, so there is nothing to attribute it to.
 */
export type EngagementIdResolver = (threadId: string, messageId: string | undefined, options: {
    awaitThread: boolean;
}) => EngagementEventIds | undefined | Promise<EngagementEventIds | undefined>;
/**
 * Derives engagement events from what a chat integration observes and keeps
 * the per thread state the events need: a run's start for the stop duration,
 * a run's end for the time to the next message, one error and one suggestion
 * list per run or thread. A started run is kept until it ends or stops; the
 * rest is kept for the 256 most recently touched threads, so a long session
 * does not grow it without bound. Delivery goes through the cloud's event
 * buffer, so a disabled telemetry setting drops everything here as well.
 */
export declare class CloudEngagementReporter {
    private readonly runStartedAt;
    private readonly runEndedAt;
    private readonly shownErrors;
    private readonly shownSuggestions;
    private readonly getCloud;
    private readonly resolveIds;
    constructor(cloud: AssistantCloud | (() => AssistantCloud), resolveIds?: EngagementIdResolver);
    runStarted(threadId: string): void;
    runEnded(threadId: string): void;
    /** Reported once per started run, with the time the run had been going. */
    runStopped(threadId: string): void;
    /** Carries the time since the previous run of the thread ended, when known. */
    messageSent(threadId: string, init: {
        messageId?: string | undefined;
        chars: number;
        attachments: number;
    }): void;
    messageEdited(threadId: string, init: {
        messageId: string;
        chars: number;
    }): void;
    messageRegenerated(threadId: string, messageId?: string): void;
    /** Reported once per run, so a retried render of the same error stays one event. */
    errorShown(threadId: string, init: {
        messageId?: string | undefined;
        reason: string;
    }): void;
    /** Reported once per thread, with the number of suggestions on offer. */
    suggestionsShown(threadId: string, count: number): void;
    suggestionClicked(threadId: string): void;
    attachmentAdded(threadId: string, init: {
        messageId?: string | undefined;
        contentType?: string | undefined;
    }): void;
    attachmentFailed(threadId: string, init: {
        messageId?: string | undefined;
        contentType?: string | undefined;
    }): void;
    voiceStarted(threadId: string): void;
    speechStarted(threadId: string, messageId?: string): void;
    branchSwitched(threadId: string, messageId?: string): void;
    messageCopied(threadId: string, messageId?: string): void;
    toolApproved(threadId: string, messageId: string, toolCallId: string, toolName: string): void;
    toolRejected(threadId: string, messageId: string, toolCallId: string, toolName: string): void;
    /** Reported only for a thread the cloud already knows. */
    threadSwitched(threadId: string): void;
    private track;
}