import type { AssistantCloud } from "assistant-cloud";
import type { Attachment, PendingAttachment, CompleteAttachment } from "../../../types/attachment.js";
import type { AttachmentAdapter } from "../../../adapters/attachment.js";
export declare class CloudFileAttachmentAdapter implements AttachmentAdapter {
    accept: string;
    private getCloud;
    constructor(cloud: AssistantCloud);
    constructor(getCloud: () => AssistantCloud);
    private uploadedUrls;
    private activeUploads;
    add({ file, }: {
        file: File;
    }): AsyncGenerator<PendingAttachment, void>;
    remove(attachment: Attachment): Promise<void>;
    send(attachment: PendingAttachment): Promise<CompleteAttachment>;
}