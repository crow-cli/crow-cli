import type { Attachment } from "../../types/attachment.js";
export type AttachmentAddOperation = {
    cancelled: boolean;
    attachmentIds: Set<string>;
};
export declare class AttachmentAddOperations {
    private readonly operations;
    private readonly uploading;
    start(): AttachmentAddOperation;
    accept(operation: AttachmentAddOperation, attachment: Pick<Attachment, "id" | "status">): boolean;
    finish(operation: AttachmentAddOperation): void;
    isCancelled(operation: AttachmentAddOperation): boolean;
    cancel(attachmentId: string): void;
    cancelAll(): void;
    whenSendable(attachmentId: string): Promise<void> | undefined;
    private settle;
}
export declare const drainAttachmentAdd: <T>(result: Promise<T> | AsyncIterable<T>, accept: (attachment: T) => boolean) => Promise<void>;