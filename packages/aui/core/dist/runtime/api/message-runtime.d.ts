import type { SpeechState } from "../interfaces/thread-runtime-core.js";
import type { ThreadMessage } from "../../types/message.js";
import type { Unsubscribe } from "../../types/unsubscribe.js";
import type { RunConfig } from "../../types/message.js";
import { type AttachmentRuntime, MessageAttachmentRuntimeImpl } from "./attachment-runtime.js";
import { type EditComposerRuntime, EditComposerRuntimeImpl } from "./composer-runtime.js";
import { type MessagePartRuntime, MessagePartRuntimeImpl } from "./message-part-runtime.js";
import type { MessageRuntimePath } from "./paths.js";
import type { ThreadRuntimeCoreBinding } from "./thread-runtime.js";
import type { MessageStateBinding } from "./bindings.js";
export type MessageRuntimeState = ThreadMessage & {
    readonly parentId: string | null;
    /** The position of this message in the thread (0 for first message) */
    readonly index: number;
    readonly isLast: boolean;
    readonly branchNumber: number;
    readonly branchCount: number;
    /**
     * @deprecated This API is still under active development and might change without notice.
     */
    readonly speech: SpeechState | undefined;
};
/**
 * @deprecated Use `MessageRuntimeState`. From `@assistant-ui/react` 0.16, `MessageState` names the message state read through `useAuiState`.
 */
export type MessageState = MessageRuntimeState;
export type { MessageStateBinding } from "./bindings.js";
type ReloadConfig = {
    runConfig?: RunConfig;
};
export type MessageRuntime = {
    readonly path: MessageRuntimePath;
    readonly composer: EditComposerRuntime;
    getState(): MessageRuntimeState;
    delete(): void | Promise<void>;
    reload(config?: ReloadConfig): void;
    /**
     * @deprecated This API is still under active development and might change without notice.
     */
    speak(): void;
    /**
     * @deprecated This API is still under active development and might change without notice.
     */
    stopSpeaking(): void;
    submitFeedback({ type, comment, }: {
        type: "positive" | "negative";
        comment?: string;
    }): void;
    switchToBranch({ position, branchId, }: {
        position?: "previous" | "next" | undefined;
        branchId?: string | undefined;
    }): void;
    unstable_getCopyText(): string;
    subscribe(callback: () => void): Unsubscribe;
    getMessagePartByIndex(idx: number): MessagePartRuntime;
    getMessagePartByToolCallId(toolCallId: string): MessagePartRuntime;
    getAttachmentByIndex(idx: number): AttachmentRuntime & {
        source: "message";
    };
};
export declare class MessageRuntimeImpl implements MessageRuntime {
    get path(): MessageRuntimePath;
    private _core;
    private _threadBinding;
    constructor(_core: MessageStateBinding, _threadBinding: ThreadRuntimeCoreBinding);
    protected __internal_bindMethods(): void;
    readonly composer: EditComposerRuntimeImpl;
    private _getEditComposerRuntimeCore;
    getState(): ThreadMessage & {
        readonly parentId: string | null;
        readonly index: number;
        readonly isLast: boolean;
        readonly branchNumber: number;
        readonly branchCount: number;
        readonly speech: SpeechState | undefined;
    };
    delete(): void | Promise<void>;
    reload(reloadConfig?: ReloadConfig): void;
    speak(): void;
    stopSpeaking(): void;
    submitFeedback({ type, comment, }: {
        type: "positive" | "negative";
        comment?: string;
    }): void;
    switchToBranch({ position, branchId, }: {
        position?: "previous" | "next" | undefined;
        branchId?: string | undefined;
    }): void;
    unstable_getCopyText(): string;
    subscribe(callback: () => void): Unsubscribe;
    getMessagePartByIndex(idx: number): MessagePartRuntimeImpl;
    getMessagePartByToolCallId(toolCallId: string): MessagePartRuntimeImpl;
    getAttachmentByIndex(idx: number): MessageAttachmentRuntimeImpl;
}