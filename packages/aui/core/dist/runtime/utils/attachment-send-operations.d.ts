import type { AttachmentAdapter } from "../../adapters/attachment.js";
import { type Attachment, type CompleteAttachment } from "../../types/attachment.js";
export declare class AttachmentSendOperations {
    private readonly entries;
    private readonly removed;
    markRemoved(attachment: Attachment): void;
    unmarkRemoved(attachment: Attachment): void;
    isRemoved(attachment: Attachment): boolean;
    send(attachment: Attachment, adapter: AttachmentAdapter | undefined, signal?: AbortSignal): Promise<CompleteAttachment>;
    transfer(original: Attachment, replacement: Attachment): Attachment;
}