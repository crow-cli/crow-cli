import { type Attachment, type CreateAttachment } from "../../types/attachment.js";
import type { MessageRole, AppendMessage } from "../../types/message.js";
import type { QuoteInfo } from "../../types/quote.js";
import type { RunConfig } from "../../types/message.js";
import { BaseSubscribable } from "../../subscribable/subscribable.js";
import { type AttachmentAdapter } from "../../adapters/attachment.js";
import type { ComposerRuntimeCore, ComposerSubmission, ComposerRuntimeEventCallback, ComposerRuntimeEventPayload, ComposerRuntimeEventType, DictationState, SendOptions } from "../interfaces/composer-runtime-core.js";
import type { DictationAdapter } from "../../adapters/speech.js";
import type { QueuePlacement } from "../queue/external-thread-queue-adapter.js";
import { type QueueItemState } from "../queue/queue-item.js";
export declare abstract class BaseComposerRuntimeCore extends BaseSubscribable implements ComposerRuntimeCore {
    readonly isEditing = true;
    protected abstract getAttachmentAdapter(): AttachmentAdapter | undefined;
    protected abstract getDictationAdapter(): DictationAdapter | undefined;
    protected enrichWithComposerMetadata<T extends {
        metadata?: {
            custom?: Record<string, unknown>;
        };
    }>(message: T, composerMetadata: Record<string, unknown> | undefined): T;
    get attachmentAccept(): string;
    private _attachments;
    get attachments(): readonly Attachment[];
    protected setAttachments(value: readonly Attachment[]): void;
    abstract get canCancel(): boolean;
    abstract get canSend(): boolean;
    get isEmpty(): boolean;
    private _text;
    get text(): string;
    private _role;
    get role(): "system" | "user" | "assistant";
    private _runConfig;
    get runConfig(): RunConfig;
    private _quote;
    get quote(): QuoteInfo | undefined;
    setQuote(quote: QuoteInfo | undefined): void;
    setText(value: string): void;
    private _rebaseDictation;
    setRole(role: MessageRole): void;
    setRunConfig(runConfig: RunConfig): void;
    private _submission;
    private _submissionSend;
    private _inTransit;
    private _inTransitSubmissions;
    private _sendGeneration;
    private _attachmentAddOperations;
    private _attachmentSends;
    get submission(): ComposerSubmission | undefined;
    get inTransit(): readonly ComposerSubmission[];
    /** Whether a send is still being prepared, which holds the composer. */
    protected get isSubmitting(): boolean;
    /** Whether a send takes the draft with it, leaving the composer free. */
    protected get detachesDraftOnSend(): boolean;
    /**
     * The ids of the thread's messages of a role, or undefined when this
     * composer's sends do not render in the thread. A dispatched submission
     * stays in transit until a message of its role that was not there at
     * dispatch shows up.
     */
    protected threadMessageIds(_role: MessageRole): readonly string[] | undefined;
    /**
     * Releases the messages in transit that the thread now shows. Each new
     * message stands in for the oldest send still waiting for one, and only
     * once, so sends made in quick succession hand over in order.
     */
    protected settleInTransit(): void;
    private _setInTransit;
    private _leaveTransit;
    private _cancelAttachmentAdd;
    private _cancelAllAttachmentAdds;
    private _emptyTextAndAttachments;
    private _onClearAttachments;
    reset(): Promise<void>;
    clearAttachments(): Promise<void>;
    send(options?: SendOptions): Promise<void>;
    private _prepareSubmission;
    private _dispatch;
    private _refreshSubmissionAttachments;
    private _returnSubmissionToDraft;
    /** Ends the send being prepared, so nothing it started can dispatch it. */
    private _endSubmission;
    /** Drops the send being prepared without returning it to the draft, for a thread runtime disposed for good. */
    __internal_dispose(): void;
    /**
     * Stops the submission and takes its content back into the draft, merging it
     * ahead of anything written since, so a send is never dropped.
     */
    protected cancelSubmission(): void;
    /**
     * Takes a send's content back into the draft, ahead of anything written
     * since. A composer that kept its draft only takes back the state the
     * attachments came back in, such as the reason one failed.
     */
    private _returnToDraft;
    private _discardSubmission;
    /**
     * Take a message back into the composer when it has nowhere else to live:
     * a send the runtime never dispatched, or a message a cancelled run is
     * removing from the thread. Reports whether the composer accepted it, so a
     * caller that is also removing the message can keep it instead of dropping
     * it. Refused, and left untouched, while the composer holds anything of its
     * own.
     */
    restoreDraft(draft: {
        text: string;
        quote?: QuoteInfo | undefined;
        attachments?: readonly Attachment[] | undefined;
    }): boolean;
    /**
     * Inverse of `restoreDraft`: clears the composer while it still holds
     * exactly the given draft. A draft the user has edited since is left
     * untouched.
     */
    retractDraft(draft: {
        text: string;
        quote?: QuoteInfo | undefined;
        attachments?: readonly Attachment[] | undefined;
    }): void;
    cancel(): void;
    get queue(): readonly QueueItemState[];
    moveQueueItem(_queueItemId: string, _placement: QueuePlacement): void;
    editQueueItem(_queueItemId: string, _message: AppendMessage): void;
    removeQueueItem(_queueItemId: string): void;
    protected abstract handleSend(message: Omit<AppendMessage, "parentId" | "sourceId">, options?: SendOptions): void | Promise<void>;
    protected abstract handleCancel(): void;
    addAttachment(fileOrAttachment: File | CreateAttachment): Promise<void>;
    private _safeEmitAttachmentAddError;
    removeAttachment(attachmentId: string): Promise<void>;
    /**
     * A submission is not delivered yet, so an attachment can still be taken out
     * of it, which the draft no longer holds once the send detached it.
     */
    private _removeSubmittedAttachment;
    /**
     * An attachment whose removal failed stays out of the message it was taken
     * from and shows why, so the removal can be tried again.
     */
    private _failSubmittedRemoval;
    private _dictation;
    private _dictationSession;
    private _dictationUnsubscribes;
    private _dictationBaseText;
    private _currentInterimText;
    private _dictationSessionIdCounter;
    private _activeDictationSessionId;
    private _isCleaningDictation;
    get dictation(): DictationState | undefined;
    private _isActiveSession;
    startDictation(): void;
    stopDictation(): void;
    private _stopDictationSession;
    private _cleanupDictation;
    private _eventSubscribers;
    protected _notifyEventSubscribers<E extends ComposerRuntimeEventType>(event: E, payload: ComposerRuntimeEventPayload[E]): void;
    unstable_on<E extends ComposerRuntimeEventType>(event: E, callback: ComposerRuntimeEventCallback<E>): () => void;
}