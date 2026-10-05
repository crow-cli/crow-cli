import type { Attachment, CreateAttachment } from "../../types/attachment.js";
import type { AppendMessage, MessageRole } from "../../types/message.js";
import type { QuoteInfo } from "../../types/quote.js";
import type { Unsubscribe } from "../../types/unsubscribe.js";
import type { RunConfig } from "../../types/message.js";
import type { QueueItemState } from "../queue/queue-item.js";
import type { QueuePlacement } from "../queue/external-thread-queue-adapter.js";
import type { ComposerRuntimeEventCallback, ComposerRuntimeEventType, ComposerSubmission, DictationState, SendOptions } from "../interfaces/composer-runtime-core.js";
import type { ThreadComposerRuntimeCoreBinding, EditComposerRuntimeCoreBinding, ComposerRuntimeCoreBinding } from "./bindings.js";
import type { ComposerRuntimePath } from "./paths.js";
import { type AttachmentRuntime, EditComposerAttachmentRuntimeImpl, ThreadComposerAttachmentRuntimeImpl } from "./attachment-runtime.js";
export type { ThreadComposerRuntimeCoreBinding, EditComposerRuntimeCoreBinding, ComposerRuntimeCoreBinding, };
type BaseComposerState = {
    /**
     * Whether the composer can cancel the current run. `true` when the runtime
     * supports cancel and a run is in flight, not merely when cancel is a
     * capability.
     */
    readonly canCancel: boolean;
    readonly canSend: boolean;
    readonly isEditing: boolean;
    readonly isEmpty: boolean;
    readonly text: string;
    readonly role: MessageRole;
    readonly attachments: readonly Attachment[];
    readonly runConfig: RunConfig;
    readonly attachmentAccept: string;
    /**
     * The current state of dictation.
     * Undefined when dictation is not active.
     */
    readonly dictation: DictationState | undefined;
    /**
     * The currently quoted text, if any.
     * Undefined when no quote is set.
     */
    readonly quote: QuoteInfo | undefined;
    /** Messages waiting to be processed. Empty unless the `queue` capability is set. */
    readonly queue: readonly QueueItemState[];
    /**
     * The message this composer sent while its attachments are prepared.
     * Undefined once the runtime has taken it.
     */
    readonly submission?: ComposerSubmission | undefined;
    /**
     * Messages this composer handed to the runtime that the thread does not
     * show yet, oldest first. The thread keeps rendering each one until the
     * runtime shows the message it became.
     */
    readonly inTransit?: readonly ComposerSubmission[] | undefined;
};
export type ThreadComposerState = BaseComposerState & {
    readonly type: "thread";
};
export type EditComposerState = BaseComposerState & {
    readonly type: "edit";
    readonly parentId: string | null;
    readonly sourceId: string | null;
};
export type ComposerRuntimeState = ThreadComposerState | EditComposerState;
/**
 * @deprecated Use `ComposerRuntimeState`. From `@assistant-ui/react` 0.16, `ComposerState` names the composer state read through `useAuiState`.
 */
export type ComposerState = ComposerRuntimeState;
export type ComposerRuntime = {
    readonly path: ComposerRuntimePath;
    readonly type: "edit" | "thread";
    /**
     * Get the current state of the composer. Includes any data that has been added to the composer.
     */
    getState(): ComposerRuntimeState;
    /**
     * Add an attachment to the composer. Accepts either a standard File object
     * (processed through the AttachmentAdapter) or a CreateAttachment descriptor
     * for external-source attachments (URLs, API data, CMS references). External
     * descriptors bypass the adapter's `add()` step but still respect
     * `adapter.accept` when an adapter is configured; without an adapter they
     * are added as-is.
     * @param fileOrAttachment The file or attachment descriptor to add.
     */
    addAttachment(fileOrAttachment: File | CreateAttachment): Promise<void>;
    /**
     * Set the text of the composer.
     * @param text The text to set in the composer.
     */
    setText(text: string): void;
    /**
     * Set the role of the composer. For instance, if you'd like a specific message to have the 'assistant' role, you can do so here.
     * @param role The role to set in the composer.
     */
    setRole(role: MessageRole): void;
    /**
     * Set the run config of the composer. This is used to send custom configuration data to the model.
     * Within your backend, you can use the `runConfig` object.
     * Example:
     * ```ts
     * composerRuntime.setRunConfig({
     *   custom: { customField: "customValue" }
     * });
     * ```
     * @param runConfig The run config to set in the composer.
     */
    setRunConfig(runConfig: RunConfig): void;
    /**
     * Reset the composer. This will clear the entire state of the composer, including all text and attachments.
     */
    reset(): Promise<void>;
    /**
     * Clear all attachments from the composer.
     */
    clearAttachments(): Promise<void>;
    /**
     * Send a message. This will send whatever text or attachments are in the composer.
     * @param options Optional send options. Use `{ startRun: true }` to force starting a new run.
     */
    send(options?: SendOptions): void;
    /**
     * Cancel the current run. In edit mode, this will exit edit mode.
     */
    cancel(): void;
    /** @deprecated Use `moveQueueItem(queueItemId, { lane: "steer", insertAfter: null })` instead. Removal after 2026-11-05. */
    steerQueueItem(queueItemId: string): void;
    /** Move a queued message between lanes or within a lane. */
    moveQueueItem(queueItemId: string, placement: QueuePlacement): void;
    /** Replace the message a queued item dispatches, keeping its lane position. */
    editQueueItem(queueItemId: string, message: AppendMessage): void;
    /** Remove a queued message. */
    removeQueueItem(queueItemId: string): void;
    /**
     * Listens for changes to the composer state.
     * @param callback The callback to call when the composer state changes.
     */
    subscribe(callback: () => void): Unsubscribe;
    /**
     * Get an attachment by index.
     * @param idx The index of the attachment to get.
     */
    getAttachmentByIndex(idx: number): AttachmentRuntime;
    /**
     * Start dictation to convert voice to text input.
     * Requires a DictationAdapter to be configured.
     */
    startDictation(): void;
    /**
     * Stop the current dictation session.
     */
    stopDictation(): void;
    /**
     * Set a quote for the next message. Pass undefined to clear.
     * @param quote The quote info to set, or undefined to clear.
     */
    setQuote(quote: QuoteInfo | undefined): void;
    /**
     * @deprecated This API is still under active development and might change without notice.
     */
    unstable_on<E extends ComposerRuntimeEventType>(event: E, callback: ComposerRuntimeEventCallback<E>): Unsubscribe;
};
export declare abstract class ComposerRuntimeImpl implements ComposerRuntime {
    get path(): ComposerRuntimePath;
    abstract get type(): "edit" | "thread";
    protected _core: ComposerRuntimeCoreBinding;
    constructor(_core: ComposerRuntimeCoreBinding);
    protected __internal_bindMethods(): void;
    abstract getState(): ComposerRuntimeState;
    setText(text: string): void;
    setRunConfig(runConfig: RunConfig): void;
    addAttachment(fileOrAttachment: File | CreateAttachment): Promise<void>;
    reset(): Promise<void>;
    clearAttachments(): Promise<void>;
    send(options?: SendOptions): void;
    cancel(): void;
    steerQueueItem(queueItemId: string): void;
    moveQueueItem(queueItemId: string, placement: QueuePlacement): void;
    editQueueItem(queueItemId: string, message: AppendMessage): void;
    removeQueueItem(queueItemId: string): void;
    setRole(role: MessageRole): void;
    startDictation(): void;
    stopDictation(): void;
    setQuote(quote: QuoteInfo | undefined): void;
    subscribe(callback: () => void): Unsubscribe;
    private _eventSubscriptionSubjects;
    unstable_on<E extends ComposerRuntimeEventType>(event: E, callback: ComposerRuntimeEventCallback<E>): Unsubscribe;
    abstract getAttachmentByIndex(idx: number): AttachmentRuntime;
}
export type ThreadComposerRuntime = Omit<ComposerRuntime, "getState" | "getAttachmentByIndex"> & {
    readonly path: ComposerRuntimePath & {
        composerSource: "thread";
    };
    readonly type: "thread";
    getState(): ThreadComposerState;
    getAttachmentByIndex(idx: number): AttachmentRuntime & {
        source: "thread-composer";
    };
};
export declare class ThreadComposerRuntimeImpl extends ComposerRuntimeImpl implements ThreadComposerRuntime {
    get path(): ComposerRuntimePath & {
        composerSource: "thread";
    };
    get type(): "thread";
    private _getState;
    constructor(core: ThreadComposerRuntimeCoreBinding);
    getState(): ThreadComposerState;
    getAttachmentByIndex(idx: number): ThreadComposerAttachmentRuntimeImpl;
}
export type EditComposerRuntime = Omit<ComposerRuntime, "getState" | "getAttachmentByIndex"> & {
    readonly path: ComposerRuntimePath & {
        composerSource: "edit";
    };
    readonly type: "edit";
    getState(): EditComposerState;
    beginEdit(): void;
    getAttachmentByIndex(idx: number): AttachmentRuntime & {
        source: "edit-composer";
    };
};
export declare class EditComposerRuntimeImpl extends ComposerRuntimeImpl implements EditComposerRuntime {
    get path(): ComposerRuntimePath & {
        composerSource: "edit";
    };
    get type(): "edit";
    private _getState;
    private _beginEdit;
    constructor(core: EditComposerRuntimeCoreBinding, _beginEdit: () => void);
    __internal_bindMethods(): void;
    getState(): EditComposerState;
    beginEdit(): void;
    getAttachmentByIndex(idx: number): EditComposerAttachmentRuntimeImpl;
}