import type { ThreadMessage } from "../../types/message.js";
import type { SubscribableWithState } from "../../subscribable/subscribable.js";
import type { ComposerRuntimeCore, EditComposerRuntimeCore, ThreadComposerRuntimeCore } from "../interfaces/composer-runtime-core.js";
import type { SpeechState } from "../interfaces/thread-runtime-core.js";
import type { ComposerRuntimePath, MessageRuntimePath } from "./paths.js";
export type ComposerRuntimeCoreBinding = SubscribableWithState<ComposerRuntimeCore | undefined, ComposerRuntimePath>;
export type ThreadComposerRuntimeCoreBinding = SubscribableWithState<ThreadComposerRuntimeCore | undefined, ComposerRuntimePath & {
    composerSource: "thread";
}>;
export type EditComposerRuntimeCoreBinding = SubscribableWithState<EditComposerRuntimeCore | undefined, ComposerRuntimePath & {
    composerSource: "edit";
}>;
export type MessageStateBinding = SubscribableWithState<ThreadMessage & {
    readonly parentId: string | null;
    readonly index: number;
    readonly isLast: boolean;
    readonly branchNumber: number;
    readonly branchCount: number;
    readonly speech: SpeechState | undefined;
}, MessageRuntimePath>;
export type ThreadListItemRuntimeState = {
    readonly isMain: boolean;
    /**
     * Whether this thread has a run in progress, including a run that continues
     * after the user switches to another thread.
     */
    readonly isRunning: boolean;
    readonly id: string;
    readonly remoteId: string | undefined;
    readonly externalId: string | undefined;
    readonly status: import("../interfaces/thread-list-runtime-core.js").ThreadListItemStatus;
    readonly title?: string | undefined;
    readonly lastMessageAt?: Date | undefined;
    readonly custom?: Record<string, unknown> | undefined;
};
/**
 * @deprecated Use `ThreadListItemRuntimeState`. From `@assistant-ui/react` 0.16, `ThreadListItemState` names the thread list item state read through `useAuiState`.
 */
export type ThreadListItemState = ThreadListItemRuntimeState;