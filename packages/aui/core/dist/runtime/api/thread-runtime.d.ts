import type { ThreadSuggestion, RuntimeCapabilities, ThreadRuntimeCore, SpeechState, VoiceSessionState, ThreadRuntimeEventCallback, ThreadRuntimeEventType, StartRunConfig, ResumeRunConfig } from "../interfaces/thread-runtime-core.js";
import type { ExportedMessageRepository } from "../utils/message-repository.js";
import type { ThreadMessageLike } from "../utils/thread-message-like.js";
import { type MessageRuntime, MessageRuntimeImpl } from "./message-runtime.js";
import type { SubscribableWithState } from "../../subscribable/subscribable.js";
import { type ThreadComposerRuntime, ThreadComposerRuntimeImpl } from "./composer-runtime.js";
import type { ThreadListItemRuntimePath, ThreadRuntimePath } from "./paths.js";
import type { ThreadListItemRuntimeState } from "./bindings.js";
import type { AppendMessage, ThreadMessage } from "../../types/message.js";
import type { Unsubscribe } from "../../types/unsubscribe.js";
import type { RunConfig } from "../../types/message.js";
import type { ModelContext } from "../../model-context/types.js";
import type { ChatModelRunOptions, ChatModelRunResult } from "../utils/chat-model-adapter.js";
import type { ReadonlyJSONValue } from "assistant-stream/utils";
export type CreateStartRunConfig = {
    parentId: string | null;
    sourceId?: string | null | undefined;
    runConfig?: RunConfig | undefined;
};
export type CreateResumeRunConfig = CreateStartRunConfig & {
    stream?: (options: ChatModelRunOptions) => AsyncGenerator<ChatModelRunResult, void, unknown>;
};
export type CreateAppendMessage = string | {
    /**
     * An omitted value or `undefined` selects the current tail.
     * `null` selects a root branch.
     */
    parentId?: string | null | undefined;
    sourceId?: string | null | undefined;
    role?: AppendMessage["role"] | undefined;
    content: AppendMessage["content"];
    attachments?: AppendMessage["attachments"] | undefined;
    metadata?: AppendMessage["metadata"] | undefined;
    createdAt?: Date | undefined;
    runConfig?: AppendMessage["runConfig"] | undefined;
    startRun?: boolean | undefined;
};
export type ThreadRuntimeCoreBinding = SubscribableWithState<ThreadRuntimeCore, ThreadRuntimePath> & {
    outerSubscribe(callback: () => void): Unsubscribe;
};
export type ThreadListItemRuntimeBinding = SubscribableWithState<ThreadListItemRuntimeState, ThreadListItemRuntimePath>;
export type ThreadRuntimeState = {
    /**
     * The thread ID.
     * @deprecated This field is deprecated and will be removed in 0.12.0. Use `useThreadListItem().id` instead.
     */
    readonly threadId: string;
    /**
     * The thread metadata.
     *
     * @deprecated Use `useThreadListItem()` instead. This field is deprecated and will be removed in 0.12.0.
     */
    readonly metadata: ThreadListItemRuntimeState;
    /**
     * Whether the thread is disabled. Disabled threads cannot receive new messages.
     */
    readonly isDisabled: boolean;
    /**
     * Whether the thread is loading its history.
     */
    readonly isLoading: boolean;
    /**
     * Whether the thread is running. A thread is considered running when there is an active stream connection to the backend.
     */
    readonly isRunning: boolean;
    /**
     * The capabilities of the thread, such as whether the thread supports editing, branch switching, etc.
     */
    readonly capabilities: RuntimeCapabilities;
    /**
     * The messages in the currently selected branch of the thread.
     */
    readonly messages: readonly ThreadMessage[];
    /**
     * The thread state.
     *
     * @deprecated This feature is experimental
     */
    readonly state: ReadonlyJSONValue;
    /**
     * Follow up message suggestions to show the user.
     */
    readonly suggestions: readonly ThreadSuggestion[];
    /**
     * Custom extra information provided by the runtime.
     */
    readonly extras: unknown;
    /**
     * @deprecated This API is still under active development and might change without notice.
     */
    readonly speech: SpeechState | undefined;
    readonly voice: VoiceSessionState | undefined;
};
/**
 * @deprecated Use `ThreadRuntimeState`. From `@assistant-ui/react` 0.16, `ThreadState` names the thread state read through `useAuiState`.
 */
export type ThreadState = ThreadRuntimeState;
/**
 * The canonical `isRunning` derivation. A runtime that tracks run state itself
 * reports it directly; the rest fall back to the trailing assistant message.
 */
export declare const getThreadRuntimeCoreIsRunning: (runtime: Pick<ThreadRuntimeCore, "isRunning" | "messages">) => boolean;
export declare const getThreadState: (runtime: ThreadRuntimeCore, threadListItemState: ThreadListItemRuntimeState) => ThreadRuntimeState;
export type ThreadRuntime = {
    /**
     * The selector for the thread runtime.
     */
    readonly path: ThreadRuntimePath;
    /**
     * The thread composer runtime.
     */
    readonly composer: ThreadComposerRuntime;
    /**
     * Gets a snapshot of the thread state.
     */
    getState(): ThreadRuntimeState;
    /**
     * Append a new message to the thread.
     *
     * @example ```ts
     * // append a new user message with the text "Hello, world!"
     * threadRuntime.append("Hello, world!");
     * ```
     *
     * @example ```ts
     * // append a new assistant message with the text "Hello, world!"
     * threadRuntime.append({
     *   role: "assistant",
     *   content: [{ type: "text", text: "Hello, world!" }],
     * });
     * ```
     */
    append(message: CreateAppendMessage): void;
    deleteMessage(messageId: string): void | Promise<void>;
    /**
     * Start a new run with the given configuration.
     * @param config The configuration for starting the run
     */
    startRun(config: CreateStartRunConfig): void;
    /**
     * Resume a run with the given configuration.
     * @param config The configuration for resuming the run
     **/
    resumeRun(config: CreateResumeRunConfig): void;
    /**
     * Export the thread state in the external store format.
     * For AI SDK runtimes, this returns the AI SDK message format.
     * For other runtimes, this may return different formats or throw an error.
     * @returns The thread state in the external format (typed as any)
     */
    exportExternalState(): any;
    /**
     * Import thread state from the external store format.
     * For AI SDK runtimes, this accepts AI SDK messages.
     * For other runtimes, this may accept different formats or throw an error.
     * @param state The thread state in the external format (typed as any)
     */
    importExternalState(state: any): void;
    subscribe(callback: () => void): Unsubscribe;
    cancelRun(): void;
    /**
     * Notifies the runtime that the adapter discarded its backing session.
     * Clears session-scoped tool-invocation state without run-cancel side
     * effects such as composer draft restoration. Internal API for
     * external-store adapter authors.
     */
    unstable_notifySessionReset(): void;
    getModelContext(): ModelContext;
    export(): ExportedMessageRepository;
    import(repository: ExportedMessageRepository): void;
    /**
     * Reset the thread with optional initial messages.
     *
     * @param initialMessages - Optional array of initial messages to populate the thread
     */
    reset(initialMessages?: readonly ThreadMessageLike[]): void;
    getMessageByIndex(idx: number): MessageRuntime;
    getMessageById(messageId: string): MessageRuntime;
    /**
     * @deprecated This API is still under active development and might change without notice.
     */
    stopSpeaking(): void;
    connectVoice(): void;
    disconnectVoice(): void;
    getVoiceVolume(): number;
    subscribeVoiceVolume(callback: () => void): Unsubscribe;
    muteVoice(): void;
    unmuteVoice(): void;
    unstable_on<E extends ThreadRuntimeEventType>(event: E, callback: ThreadRuntimeEventCallback<E>): Unsubscribe;
};
export declare class ThreadRuntimeImpl implements ThreadRuntime {
    get path(): ThreadRuntimePath;
    get __internal_threadBinding(): import("../../internal.js").Subscribable & {
        path: ThreadRuntimePath;
        getState: () => Readonly<{
            getMessageById: (messageId: string) => {
                parentId: string | null;
                message: ThreadMessage;
                index: number;
            } | undefined;
            getBranches: (messageId: string) => readonly string[];
            switchToBranch: (branchId: string) => void;
            append: (message: AppendMessage) => void;
            deleteMessage: (messageId: string) => void | Promise<void>;
            startRun: (config: StartRunConfig) => void;
            resumeRun: (config: ResumeRunConfig) => void;
            cancelRun: () => void;
            unstable_notifySessionReset: () => void;
            addToolResult: (options: import("../../index.js").AddToolResultOptions) => void;
            resumeToolCall: (options: import("../../index.js").ResumeToolCallOptions) => void;
            respondToToolApproval: (options: import("../../index.js").RespondToToolApprovalOptions) => Promise<void>;
            unstable_recordToolInteraction?: (options: import("../../index.js").Unstable_RecordToolInteractionOptions) => Promise<void>;
            speak: (messageId: string) => void;
            stopSpeaking: () => void;
            connectVoice: () => void;
            disconnectVoice: () => void;
            muteVoice: () => void;
            unmuteVoice: () => void;
            submitFeedback: (feedback: import("../../index.js").SubmitFeedbackOptions) => void;
            getModelContext: () => ModelContext;
            composer: Readonly<{
                isEditing: boolean;
                canCancel: boolean;
                canSend: boolean;
                isEmpty: boolean;
                attachments: readonly import("../../index.js").Attachment[];
                attachmentAccept: string;
                addAttachment: (fileOrAttachment: File | import("../../index.js").CreateAttachment) => Promise<void>;
                removeAttachment: (attachmentId: string) => Promise<void>;
                text: string;
                setText: (value: string) => void;
                role: import("../../index.js").MessageRole;
                setRole: (role: import("../../index.js").MessageRole) => void;
                runConfig: RunConfig;
                setRunConfig: (runConfig: RunConfig) => void;
                quote: import("../../index.js").QuoteInfo | undefined;
                setQuote: (quote: import("../../index.js").QuoteInfo | undefined) => void;
                reset: () => Promise<void>;
                clearAttachments: () => Promise<void>;
                send: (options?: import("../../index.js").SendOptions) => void;
                cancel: () => void;
                submission?: import("../../index.js").ComposerSubmission | undefined;
                inTransit?: readonly import("../../index.js").ComposerSubmission[] | undefined;
                queue: readonly import("../queue/queue-item.js").QueueItemState[];
                moveQueueItem: (queueItemId: string, placement: import("../../index.js").QueuePlacement) => void;
                editQueueItem: (queueItemId: string, message: AppendMessage) => void;
                removeQueueItem: (queueItemId: string) => void;
                dictation: import("../../index.js").DictationState | undefined;
                startDictation: () => void;
                stopDictation: () => void;
                subscribe: (callback: () => void) => Unsubscribe;
                unstable_on: <E extends import("../../index.js").ComposerRuntimeEventType>(event: E, callback: import("../../index.js").ComposerRuntimeEventCallback<E>) => Unsubscribe;
            }>;
            getEditComposer: (messageId: string) => import("../../index.js").EditComposerRuntimeCore | undefined;
            beginEdit: (messageId: string) => void;
            getQueueItems?: () => readonly import("../queue/queue-item.js").QueueItemState[];
            getSteerQueueItems?: () => readonly import("../queue/queue-item.js").QueueItemState[];
            moveQueueItem?: (queueItemId: string, placement: import("../../index.js").QueuePlacement) => void;
            editQueueItem?: (queueItemId: string, message: AppendMessage) => void;
            removeQueueItem?: (queueItemId: string) => void;
            speech: SpeechState | undefined;
            voice: VoiceSessionState | undefined;
            capabilities: Readonly<RuntimeCapabilities>;
            isDisabled: boolean;
            isSendDisabled: boolean;
            isLoading: boolean;
            isRunning?: boolean | undefined;
            messages: readonly ThreadMessage[];
            state: ReadonlyJSONValue;
            suggestions: readonly ThreadSuggestion[];
            extras: unknown;
            subscribe: (callback: () => void) => Unsubscribe;
            getVoiceVolume: () => number;
            subscribeVoiceVolume: (callback: () => void) => Unsubscribe;
            import(repository: ExportedMessageRepository): void;
            export(): ExportedMessageRepository;
            exportExternalState(): any;
            importExternalState(state: any): void;
            reset(initialMessages?: readonly ThreadMessageLike[]): void;
            unstable_refetchThread?: (() => Promise<void>) | undefined;
            unstable_on<E extends ThreadRuntimeEventType>(event: E, callback: ThreadRuntimeEventCallback<E>): Unsubscribe;
        }>;
    } & {
        outerSubscribe(callback: () => void): Unsubscribe;
    } & {
        getStateState(): ThreadRuntimeState;
    };
    private readonly _threadBinding;
    private readonly _stateBinding;
    constructor(threadBinding: ThreadRuntimeCoreBinding, threadListItemBinding: ThreadListItemRuntimeBinding);
    protected __internal_bindMethods(): void;
    readonly composer: ThreadComposerRuntimeImpl;
    getState(): ThreadRuntimeState;
    append(message: CreateAppendMessage): void;
    deleteMessage(messageId: string): void | Promise<void>;
    subscribe(callback: () => void): () => void;
    getModelContext(): ModelContext;
    startRun(config: CreateStartRunConfig): void;
    resumeRun(config: CreateResumeRunConfig): void;
    exportExternalState(): any;
    importExternalState(state: any): void;
    cancelRun(): void;
    unstable_notifySessionReset(): void;
    stopSpeaking(): void;
    connectVoice(): void;
    disconnectVoice(): void;
    getVoiceVolume(): number;
    subscribeVoiceVolume(callback: () => void): Unsubscribe;
    muteVoice(): void;
    unmuteVoice(): void;
    export(): ExportedMessageRepository;
    import(data: ExportedMessageRepository): void;
    reset(initialMessages?: readonly ThreadMessageLike[]): void;
    getMessageByIndex(idx: number): MessageRuntimeImpl;
    getMessageById(messageId: string): MessageRuntimeImpl;
    private _getMessageRuntime;
    private _eventSubscriptionSubjects;
    unstable_on<E extends ThreadRuntimeEventType>(event: E, callback: ThreadRuntimeEventCallback<E>): Unsubscribe;
}