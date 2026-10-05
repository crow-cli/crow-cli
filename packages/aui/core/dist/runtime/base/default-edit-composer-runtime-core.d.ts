import type { AppendMessage, ThreadMessage } from "../../types/message.js";
import type { AttachmentAdapter } from "../../adapters/attachment.js";
import type { DictationAdapter } from "../../adapters/speech.js";
import type { SendOptions } from "../interfaces/composer-runtime-core.js";
import type { ThreadRuntimeCore } from "../interfaces/thread-runtime-core.js";
import { BaseComposerRuntimeCore } from "./base-composer-runtime-core.js";
export declare class DefaultEditComposerRuntimeCore extends BaseComposerRuntimeCore {
    get canCancel(): boolean;
    protected get detachesDraftOnSend(): boolean;
    get canSend(): boolean;
    protected getAttachmentAdapter(): AttachmentAdapter | undefined;
    protected getDictationAdapter(): DictationAdapter | undefined;
    private _nonTextPassthrough;
    private _parentId;
    private _sourceId;
    private runtime;
    private endEditCallback;
    private _ended;
    constructor(runtime: ThreadRuntimeCore & {
        adapters?: {
            attachments?: AttachmentAdapter | undefined;
            dictation?: DictationAdapter | undefined;
        } | undefined;
    }, endEditCallback: () => void, { parentId, message }: {
        parentId: string | null;
        message: ThreadMessage;
    });
    get parentId(): string | null;
    get sourceId(): string | null;
    handleSend(message: Omit<AppendMessage, "parentId" | "sourceId">, options?: SendOptions): Promise<void>;
    handleCancel(): void;
}