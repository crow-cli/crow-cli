import type { AppendMessage, MessageRole } from "../../types/message.js";
import type { AttachmentAdapter } from "../../adapters/attachment.js";
import type { DictationAdapter } from "../../adapters/speech.js";
import type { SendOptions, ThreadComposerRuntimeCore } from "../interfaces/composer-runtime-core.js";
import type { ThreadRuntimeCore } from "../interfaces/thread-runtime-core.js";
import type { QueuePlacement } from "../queue/external-thread-queue-adapter.js";
import { type QueueItemState } from "../queue/queue-item.js";
import { BaseComposerRuntimeCore } from "./base-composer-runtime-core.js";
export declare class DefaultThreadComposerRuntimeCore extends BaseComposerRuntimeCore implements ThreadComposerRuntimeCore {
    get canCancel(): boolean;
    get canSend(): boolean;
    cancel(): void;
    protected threadMessageIds(role: MessageRole): string[];
    private _queueCache;
    get queue(): readonly QueueItemState[];
    moveQueueItem(queueItemId: string, placement: QueuePlacement): void;
    editQueueItem(queueItemId: string, message: AppendMessage): void;
    removeQueueItem(queueItemId: string): void;
    protected getAttachmentAdapter(): AttachmentAdapter | undefined;
    protected getDictationAdapter(): DictationAdapter | undefined;
    private runtime;
    constructor(runtime: Omit<ThreadRuntimeCore, "composer"> & {
        adapters?: {
            attachments?: AttachmentAdapter | undefined;
            dictation?: DictationAdapter | undefined;
        } | undefined;
    });
    connect(): import("../../index.js").Unsubscribe;
    handleSend(message: Omit<AppendMessage, "parentId" | "sourceId">, options?: SendOptions): Promise<void>;
    handleCancel(): Promise<void>;
}