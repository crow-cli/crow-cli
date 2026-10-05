import type { AppendMessage, ThreadAssistantMessage, ThreadMessage } from "../../types/message.js";
import type { Unsubscribe } from "../../types/unsubscribe.js";
import type { ModelContextProvider } from "../../model-context/types.js";
import { ExportedMessageRepository, MessageRepository } from "../utils/message-repository.js";
import { DefaultThreadComposerRuntimeCore } from "./default-thread-composer-runtime-core.js";
import type { AddToolResultOptions, ResumeToolCallOptions, RespondToToolApprovalOptions, ThreadSuggestion, SubmitFeedbackOptions, ThreadRuntimeCore, SpeechState, VoiceSessionState, RuntimeCapabilities, ThreadRuntimeEventCallback, ThreadRuntimeEventPayload, ThreadRuntimeEventType, StartRunConfig, ResumeRunConfig } from "../interfaces/thread-runtime-core.js";
import { DefaultEditComposerRuntimeCore } from "./default-edit-composer-runtime-core.js";
import type { SpeechSynthesisAdapter } from "../../adapters/speech.js";
import type { FeedbackAdapter } from "../../adapters/feedback.js";
import type { AttachmentAdapter } from "../../adapters/attachment.js";
import type { RealtimeVoiceAdapter } from "../../adapters/voice.js";
import type { ThreadMessageLike } from "../utils/thread-message-like.js";
import { BaseSubscribable } from "../../subscribable/subscribable.js";
type BaseThreadAdapters = {
    speech?: SpeechSynthesisAdapter | undefined;
    feedback?: FeedbackAdapter | undefined;
    attachments?: AttachmentAdapter | undefined;
    voice?: RealtimeVoiceAdapter | undefined;
};
export declare abstract class BaseThreadRuntimeCore extends BaseSubscribable implements ThreadRuntimeCore {
    private _isInitialized;
    protected repository: MessageRepository;
    abstract get adapters(): BaseThreadAdapters | undefined;
    abstract get isDisabled(): boolean;
    abstract get isSendDisabled(): boolean;
    abstract get isLoading(): boolean;
    abstract get suggestions(): readonly ThreadSuggestion[];
    abstract get extras(): unknown;
    abstract get capabilities(): RuntimeCapabilities;
    abstract append(message: AppendMessage): void;
    abstract deleteMessage(messageId: string): void | Promise<void>;
    abstract startRun(config: StartRunConfig): void;
    abstract resumeRun(config: ResumeRunConfig): void;
    abstract addToolResult(options: AddToolResultOptions): void;
    abstract resumeToolCall(options: ResumeToolCallOptions): void;
    abstract respondToToolApproval(options: RespondToToolApprovalOptions): Promise<void>;
    abstract cancelRun(): void;
    abstract exportExternalState(): any;
    abstract importExternalState(state: any): void;
    abstract unstable_notifySessionReset(): void;
    protected _voiceMessages: ThreadMessage[];
    protected _voiceGeneration: number;
    private _cachedMergedMessages;
    private _cachedVoiceGeneration;
    private _cachedMergedBase;
    protected _markVoiceMessagesDirty(): void;
    protected _getBaseMessages(): readonly ThreadMessage[];
    protected _commitVoiceMessage(_message: ThreadMessage): void | Promise<void>;
    protected _onMessageMetadataChanged(_previousMessage: ThreadAssistantMessage, _message: ThreadAssistantMessage): void;
    protected _dropVoiceMessage(messageId: string, notify: boolean): void;
    get messages(): readonly ThreadMessage[];
    get state(): string | number | boolean | import("assistant-stream/utils").ReadonlyJSONObject | import("assistant-stream/utils").ReadonlyJSONArray | null;
    readonly composer: DefaultThreadComposerRuntimeCore;
    private readonly _contextProvider;
    constructor(_contextProvider: ModelContextProvider);
    getModelContext(): import("../../index.js").ModelContext;
    /**
     * Stamps provider-contributed composer metadata onto an outgoing message.
     * Called at dispatch rather than in the composer, so programmatic sends are
     * covered too, and exactly once per message: a queued send is stamped when
     * it leaves the lane, never when it enters.
     *
     * Only user messages are stamped, matching the readers: both the version
     * fold and the model injection skip every other role.
     *
     * @param anchorId Message the gated branch prefix ends at. A queued send
     * passes the current tail, having waited through a run that grew the prefix
     * past the parent it was created with.
     */
    protected enrichAppendMetadata(message: AppendMessage, anchorId?: string | null): AppendMessage;
    private _editComposers;
    getEditComposer(messageId: string): DefaultEditComposerRuntimeCore | undefined;
    protected _isVoiceMessage(messageId: string | null): boolean;
    protected _resolveAppendParent(parentId: string | null): string | null;
    beginEdit(messageId: string): void;
    getMessageById(messageId: string): {
        parentId: string | null;
        message: ThreadMessage;
        index: number;
    } | undefined;
    getBranches(messageId: string): string[];
    switchToBranch(branchId: string): void;
    _notifyEventSubscribers<E extends ThreadRuntimeEventType>(event: E, payload: ThreadRuntimeEventPayload[E]): void;
    protected _notifyToolApprovalAnswered(messageId: string, toolCallId: string, toolName: string, approved: boolean): void;
    submitFeedback({ messageId, type, comment }: SubmitFeedbackOptions): void;
    private _stopSpeaking;
    speech: SpeechState | undefined;
    speak(messageId: string): void;
    stopSpeaking(): void;
    private _voiceSession;
    private _voiceUnsubs;
    voice: VoiceSessionState | undefined;
    private _voiceVolume;
    private _voiceVolumeSubscribers;
    getVoiceVolume: () => number;
    subscribeVoiceVolume: (callback: () => void) => Unsubscribe;
    protected _onVoiceConnected(): void;
    protected _onVoiceDisconnected(): void;
    private _toVoiceSessionState;
    protected _isRunActive(): boolean;
    /**
     * Waits for a pending history import before a voice message is committed.
     * The import may begin before or after the voice session connects, so the
     * loading state must be rechecked when the commit is ready to run. The wait
     * also ends when the runtime is invalidated, since a superseded runtime may
     * never learn that loading ended.
     */
    protected _getVoiceCommitBarrier(): Promise<void> | undefined;
    connectVoice(): void;
    private _currentAssistantMsg;
    private _observeVoiceCommit;
    private _handleVoiceTranscript;
    private _commitVoiceUserMessage;
    protected _appendToVoiceSession(message: AppendMessage): Promise<void>;
    private _finishVoiceAssistantMessage;
    disconnectVoice(): void;
    private _disconnectVoice;
    muteVoice(): void;
    unmuteVoice(): void;
    protected ensureInitialized(): void;
    export(): ExportedMessageRepository;
    import(data: ExportedMessageRepository): void;
    reset(initialMessages?: readonly ThreadMessageLike[]): void;
    private _eventSubscribers;
    unstable_on<E extends ThreadRuntimeEventType>(event: E, callback: ThreadRuntimeEventCallback<E>): Unsubscribe;
}
export {};