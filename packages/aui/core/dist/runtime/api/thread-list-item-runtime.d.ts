import type { Unsubscribe } from "../../types/unsubscribe.js";
import type { SubscribableWithState } from "../../subscribable/subscribable.js";
import type { ThreadListItemRuntimePath } from "./paths.js";
import type { ThreadListRuntimeCoreBinding } from "./thread-list-runtime.js";
export type ThreadListItemEventPayload = {
    /**
     * @deprecated State-derivable. Compare `s.threads.mainThreadId` against the
     * item's `s.threadListItem.id` via `useAuiState` instead. Kept for backward
     * compatibility.
     */
    switchedTo: Record<string, never>;
    /**
     * @deprecated State-derivable. Compare `s.threads.mainThreadId` against the
     * item's `s.threadListItem.id` via `useAuiState` instead. Kept for backward
     * compatibility.
     */
    switchedAway: Record<string, never>;
};
export type ThreadListItemEventType = keyof ThreadListItemEventPayload;
export type ThreadListItemEventCallback<E extends ThreadListItemEventType> = (payload: ThreadListItemEventPayload[E]) => void;
import type { ThreadListItemRuntimeState } from "./bindings.js";
import type { ThreadListItemStatus } from "../interfaces/thread-list-runtime-core.js";
export type { ThreadListItemRuntimeState, ThreadListItemStatus };
export type ThreadListItemGenerateTitleOptions = {
    /** Marks a generation started by the automatic title trigger. */
    automatic?: boolean;
};
export type ThreadListItemRuntime = {
    readonly path: ThreadListItemRuntimePath;
    getState(): ThreadListItemRuntimeState;
    initialize(): Promise<{
        remoteId: string;
        externalId: string | undefined;
    }>;
    generateTitle(options?: ThreadListItemGenerateTitleOptions): Promise<void>;
    switchTo(options?: {
        unarchive?: boolean;
    }): Promise<void>;
    rename(newTitle: string): Promise<void>;
    updateCustom(custom: Record<string, unknown> | undefined): Promise<void>;
    archive(): Promise<void>;
    unarchive(): Promise<void>;
    delete(): Promise<void>;
    detach(): void;
    subscribe(callback: () => void): Unsubscribe;
    unstable_on<E extends ThreadListItemEventType>(event: E, callback: ThreadListItemEventCallback<E>): Unsubscribe;
    __internal_getRuntime(): ThreadListItemRuntime;
};
export type ThreadListItemStateBinding = SubscribableWithState<ThreadListItemRuntimeState, ThreadListItemRuntimePath>;
export declare class ThreadListItemRuntimeImpl implements ThreadListItemRuntime {
    get path(): ThreadListItemRuntimePath;
    private _core;
    private _threadListBinding;
    constructor(_core: ThreadListItemStateBinding, _threadListBinding: ThreadListRuntimeCoreBinding);
    protected __internal_bindMethods(): void;
    getState(): ThreadListItemRuntimeState;
    switchTo(options?: {
        unarchive?: boolean;
    }): Promise<void>;
    rename(newTitle: string): Promise<void>;
    updateCustom(custom: Record<string, unknown> | undefined): Promise<void>;
    archive(): Promise<void>;
    unarchive(): Promise<void>;
    delete(): Promise<void>;
    initialize(): Promise<{
        remoteId: string;
        externalId: string | undefined;
    }>;
    generateTitle(options?: ThreadListItemGenerateTitleOptions): Promise<void>;
    unstable_on<E extends ThreadListItemEventType>(event: E, callback: ThreadListItemEventCallback<E>): Unsubscribe;
    subscribe(callback: () => void): Unsubscribe;
    detach(): void;
    __internal_getRuntime(): ThreadListItemRuntime;
}