import type { Attachment, PendingAttachment, CompleteAttachment } from "../types/attachment.js";
import type { ThreadUserMessagePart } from "../types/message.js";
export type AttachmentAdapter = {
    accept: string;
    add(state: {
        file: File;
    }): Promise<PendingAttachment> | AsyncGenerator<PendingAttachment, void>;
    remove(attachment: Attachment): Promise<void>;
    send(attachment: PendingAttachment, options?: {
        signal?: AbortSignal;
    }): Promise<CompleteAttachment>;
};
export declare class SimpleImageAttachmentAdapter implements AttachmentAdapter {
    accept: string;
    add(state: {
        file: File;
    }): Promise<PendingAttachment>;
    send(attachment: PendingAttachment, options?: {
        signal?: AbortSignal;
    }): Promise<CompleteAttachment>;
    remove(): Promise<void>;
}
export declare const getFileDataURL: (file: File, options?: {
    signal?: AbortSignal;
}) => Promise<string>;
export declare class SimpleTextAttachmentAdapter implements AttachmentAdapter {
    accept: string;
    add(state: {
        file: File;
    }): Promise<PendingAttachment>;
    send(attachment: PendingAttachment, options?: {
        signal?: AbortSignal;
    }): Promise<CompleteAttachment>;
    remove(): Promise<void>;
}
export declare function fileMatchesAccept(file: {
    name: string;
    type: string;
}, acceptString: string): boolean;
export declare function attachmentsEqual(a: readonly CompleteAttachment[], b: readonly CompleteAttachment[]): boolean;
export declare function partToCompleteAttachment(part: Exclude<ThreadUserMessagePart, {
    type: "text";
}>): CompleteAttachment;
export declare function liftNonTextParts(content: readonly ThreadUserMessagePart[]): CompleteAttachment[];
export declare class CompositeAttachmentAdapter implements AttachmentAdapter {
    private _adapters;
    accept: string;
    constructor(adapters: AttachmentAdapter[]);
    add(state: {
        file: File;
    }): Promise<PendingAttachment> | AsyncGenerator<PendingAttachment, void, any>;
    send(attachment: PendingAttachment, options?: {
        signal?: AbortSignal;
    }): Promise<CompleteAttachment>;
    remove(attachment: Attachment): Promise<void>;
}