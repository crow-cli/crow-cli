import type { Attachment, CompleteAttachment } from "../../types/attachment.js";
import type { Unsubscribe } from "../../types/unsubscribe.js";
import type { SubscribableWithState } from "../../subscribable/subscribable.js";
import type { ComposerRuntimeCoreBinding } from "./bindings.js";
import type { AttachmentRuntimePath } from "./paths.js";
type MessageAttachmentState = CompleteAttachment & {
    readonly source: "message";
};
type ThreadComposerAttachmentState = Attachment & {
    readonly source: "thread-composer";
};
type EditComposerAttachmentState = Attachment & {
    readonly source: "edit-composer";
};
export type AttachmentRuntimeState = ThreadComposerAttachmentState | EditComposerAttachmentState | MessageAttachmentState;
/**
 * @deprecated Use `AttachmentRuntimeState`. From `@assistant-ui/react` 0.16, `AttachmentState` names the attachment state read through `useAuiState`.
 */
export type AttachmentState = AttachmentRuntimeState;
type AttachmentSnapshotBinding<Source extends AttachmentRuntimeSource> = SubscribableWithState<AttachmentRuntimeState & {
    source: Source;
}, AttachmentRuntimePath & {
    attachmentSource: Source;
}>;
type AttachmentRuntimeSource = AttachmentRuntimeState["source"];
export type AttachmentRuntime<TSource extends AttachmentRuntimeSource = AttachmentRuntimeSource> = {
    readonly path: AttachmentRuntimePath & {
        attachmentSource: TSource;
    };
    readonly source: TSource;
    getState(): AttachmentRuntimeState & {
        source: TSource;
    };
    remove(): Promise<void>;
    subscribe(callback: () => void): Unsubscribe;
};
export declare abstract class AttachmentRuntimeImpl<Source extends AttachmentRuntimeSource = AttachmentRuntimeSource> implements AttachmentRuntime {
    get path(): AttachmentRuntimePath & {
        attachmentSource: Source;
    };
    abstract get source(): Source;
    private _core;
    constructor(_core: AttachmentSnapshotBinding<Source>);
    protected __internal_bindMethods(): void;
    getState(): AttachmentRuntimeState & {
        source: Source;
    };
    abstract remove(): Promise<void>;
    subscribe(callback: () => void): Unsubscribe;
}
declare abstract class ComposerAttachmentRuntime<Source extends "thread-composer" | "edit-composer"> extends AttachmentRuntimeImpl<Source> {
    private _composerApi;
    constructor(core: AttachmentSnapshotBinding<Source>, _composerApi: ComposerRuntimeCoreBinding);
    remove(): Promise<void>;
}
export declare class ThreadComposerAttachmentRuntimeImpl extends ComposerAttachmentRuntime<"thread-composer"> {
    get source(): "thread-composer";
}
export declare class EditComposerAttachmentRuntimeImpl extends ComposerAttachmentRuntime<"edit-composer"> {
    get source(): "edit-composer";
}
export declare class MessageAttachmentRuntimeImpl extends AttachmentRuntimeImpl<"message"> {
    get source(): "message";
    remove(): never;
}
export {};