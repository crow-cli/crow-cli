import type { AppendMessage, ThreadMessage } from "../../types/message.js";
import type { AddToolResultOptions, ResumeRunConfig, ResumeToolCallOptions, RespondToToolApprovalOptions, StartRunConfig, ThreadSuggestion, Unstable_RecordToolInteractionOptions } from "../../runtime/interfaces/thread-runtime-core.js";
import type { ExternalStoreAdapter } from "./external-store-adapter.js";
import { type ThreadMessageLike } from "../../runtime/utils/thread-message-like.js";
import type { RuntimeCapabilities, ThreadRuntimeCore } from "../../runtime/interfaces/thread-runtime-core.js";
import type { QueuePlacement } from "../../runtime/queue/external-thread-queue-adapter.js";
import { BaseThreadRuntimeCore } from "../../runtime/base/base-thread-runtime-core.js";
import type { ModelContextProvider } from "../../model-context/types.js";
import { ExportedMessageRepository } from "../../runtime/utils/message-repository.js";
export declare const hasUpcomingMessage: (isRunning: boolean, messages: readonly ThreadMessage[]) => boolean;
export declare class ExternalStoreThreadRuntimeCore extends BaseThreadRuntimeCore implements ThreadRuntimeCore {
    private _capabilities;
    get capabilities(): RuntimeCapabilities;
    private _messages;
    isDisabled: boolean;
    isSendDisabled: boolean;
    get isLoading(): boolean;
    get isRunning(): boolean | undefined;
    protected _getBaseMessages(): readonly ThreadMessage[];
    get state(): string | number | boolean | import("assistant-stream/utils").ReadonlyJSONObject | import("assistant-stream/utils").ReadonlyJSONArray | null;
    get adapters(): {
        attachments?: import("../../index.js").AttachmentAdapter | undefined;
        speech?: import("../../index.js").SpeechSynthesisAdapter | undefined;
        dictation?: import("../../index.js").DictationAdapter | undefined;
        voice?: import("../../index.js").RealtimeVoiceAdapter | undefined;
        feedback?: import("../../index.js").FeedbackAdapter | undefined;
        threadList?: import("./external-store-adapter.js").ExternalStoreThreadListAdapter | undefined;
    } | undefined;
    get unstable_refetchThread(): (() => Promise<void>) | undefined;
    suggestions: readonly ThreadSuggestion[];
    extras: unknown;
    private _converter;
    private _pendingDeleteEvictions;
    private _optimistic;
    private _store;
    private _getInitializePromise?;
    __internal_setGetInitializePromise(getPromise: () => Promise<unknown> | undefined): void;
    private _transformedQueue;
    /**
     * Client-side tool-invocations pipeline. Constructed lazily on first
     * snapshot — only when `adapter.unstable_enableToolInvocations === true`.
     */
    private _toolInvocations;
    private _toolStatuses;
    private _effectiveIsRunning;
    private _inTrackerUpdate;
    private _pendingRunningRefresh;
    /**
     * Tracker mutations initiated by this class (setState, reset) can publish
     * status changes synchronously. Re-entering the snapshot pipeline from
     * inside them would feed the tracker a stale snapshot and consume the
     * restore arming a reset just installed, so the running refresh is
     * deferred until the mutation returns and stays off the tracker.
     */
    private _runTrackerUpdate;
    private _refreshEffectiveIsRunning;
    private _hasExecutingTools;
    private _getEffectiveIsRunning;
    beginEdit(messageId: string): void;
    constructor(contextProvider: ModelContextProvider, store: ExternalStoreAdapter<any>);
    __internal_setAdapter(store: ExternalStoreAdapter<any>): void;
    private _updateStoreSnapshot;
    /**
     * Feed the current message snapshot into the tool-invocations tracker.
     * Opt-in via `adapter.unstable_enableToolInvocations: true`. The tracker
     * itself is fail-silent — see ToolInvocationTracker for the
     * state-transition contract.
     */
    private _driveToolInvocations;
    /**
     * Lookup table from `toolCallId` to the owning assistant message's `id`,
     * rebuilt lazily when `_messages` changes (see `_messagesForToolCallIndex`).
     */
    private _toolCallToMessageId;
    private _messagesForToolCallIndex;
    /**
     * Look up the assistant message that owns a tool-call part. Lazily builds
     * (and caches) a `toolCallId → messageId` map keyed off the current
     * `_messages` reference, so onResult dispatches stay O(1) instead of
     * walking the full thread on every result.
     */
    private _findMessageIdForToolCall;
    switchToBranch(branchId: string): void;
    /**
     * Emit `unstable_onBranchChange` for an explicit branch switch. Reads the
     * canonical head from the repository (which skips optimistic/transient
     * messages) and de-dupes switches that leave the canonical head unchanged.
     * Comparing against the head observed just before the switch — rather than the
     * last emitted head — keeps a switch firing after an adapter resync moved the
     * head elsewhere in the meantime.
     */
    private _notifyBranchChange;
    append(rawMessage: AppendMessage): Promise<void>;
    protected _commitVoiceMessage(message: ThreadMessage): void | Promise<void>;
    deleteMessage(messageId: string): Promise<void>;
    private _evictDeletedMessage;
    private _publishRepositoryMessages;
    getQueueItems(): readonly import("../../store/index.js").QueueItemState[];
    getSteerQueueItems(): readonly import("../../store/index.js").QueueItemState[];
    moveQueueItem(queueItemId: string, placement: QueuePlacement): void;
    editQueueItem(queueItemId: string, message: AppendMessage): void;
    removeQueueItem(queueItemId: string): void;
    startRun(config: StartRunConfig): Promise<void>;
    resumeRun(config: ResumeRunConfig): Promise<void>;
    exportExternalState(): any;
    importExternalState(state: any): void;
    /**
     * Adapter-facing notification that the backing session was discarded.
     * Clears session-scoped tool-invocation state and parks queued work,
     * without run-cancel semantics (`onCancel`, composer draft restoration).
     */
    unstable_notifySessionReset(): void;
    cancelRun(): void;
    private dropEmptyOptimisticHead;
    addToolResult(options: AddToolResultOptions): void;
    resumeToolCall(options: ResumeToolCallOptions): void;
    respondToToolApproval(options: RespondToToolApprovalOptions): Promise<void>;
    unstable_recordToolInteraction(options: Unstable_RecordToolInteractionOptions): Promise<void>;
    reset(initialMessages?: readonly ThreadMessageLike[]): void;
    import(data: ExportedMessageRepository): void;
    private updateMessages;
}