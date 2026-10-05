import type { Unsubscribe } from "../../types/unsubscribe.js";
import type { ThreadListRuntimeCore, ThreadListRuntimeEvent } from "../interfaces/thread-list-runtime-core.js";
import { type ThreadListItemRuntime, ThreadListItemRuntimeImpl, type ThreadListItemRuntimeState } from "./thread-list-item-runtime.js";
import { type ThreadListItemRuntimeBinding, type ThreadRuntime, type ThreadRuntimeCoreBinding } from "./thread-runtime.js";
export type ThreadListState = {
    readonly mainThreadId: string;
    readonly newThreadId: string | undefined;
    readonly threadIds: readonly string[];
    readonly archivedThreadIds: readonly string[];
    readonly isLoading: boolean;
    /** The error thrown by the most recent thread list load that failed, cleared when a later load starts. */
    readonly loadError: unknown;
    readonly isLoadingMore: boolean;
    readonly hasMore: boolean;
    readonly threadItems: Readonly<Record<string, Omit<ThreadListItemRuntimeState, "isMain" | "threadId" | "isRunning">>>;
};
export type ThreadListRuntime = {
    getState(): ThreadListState;
    subscribe(callback: () => void): Unsubscribe;
    readonly main: ThreadRuntime;
    getById(threadId: string): ThreadRuntime;
    readonly mainItem: ThreadListItemRuntime;
    getItemById(threadId: string): ThreadListItemRuntime;
    getItemByIndex(idx: number): ThreadListItemRuntime;
    getArchivedItemByIndex(idx: number): ThreadListItemRuntime;
    switchToThread(threadId: string, options?: {
        unarchive?: boolean;
    }): Promise<void>;
    switchToNewThread(): Promise<void>;
    /**
     * Observes lifecycle events on every thread this list keeps alive, so an
     * event that fires while its thread is not selected stays observable. Thread
     * lists that mount only the main thread never emit; their main thread's
     * runtime is observed directly.
     */
    unstable_subscribeThreadEvents(callback: (event: ThreadListRuntimeEvent) => void): Unsubscribe;
    getLoadThreadsPromise(): Promise<void>;
    reload(): Promise<void>;
    /**
     * Refetches the open thread's remote state, for state that changed out of
     * band and so never reached the stream. When the runtime declares the
     * in-place capability (`unstable_refetchThread`), composer drafts survive,
     * existing messages stay rendered during the refetch, and the promise
     * settles with the refetch, rejecting if it fails; that runtime also owns
     * what happens to a run in progress, since this does not stop one. Runtimes
     * without the capability have their hook remounted instead, which discards
     * unsent composer input and ends any run, and the promise resolves once the
     * new runtime attaches. A thread that has not been sent yet is left alone.
     */
    reloadMainThread(): Promise<void>;
    loadMore(): Promise<void>;
};
export type ThreadListRuntimeCoreBinding = ThreadListRuntimeCore;
export declare class ThreadListRuntimeImpl implements ThreadListRuntime {
    private _getState;
    private _stateBinding;
    private _core;
    private _runtimeFactory;
    constructor(_core: ThreadListRuntimeCoreBinding, _runtimeFactory?: new (binding: ThreadRuntimeCoreBinding, threadListItemBinding: ThreadListItemRuntimeBinding) => ThreadRuntime);
    protected __internal_bindMethods(): void;
    switchToThread(threadId: string, options?: {
        unarchive?: boolean;
    }): Promise<void>;
    switchToNewThread(): Promise<void>;
    unstable_subscribeThreadEvents(callback: (event: ThreadListRuntimeEvent) => void): Unsubscribe;
    getLoadThreadsPromise(): Promise<void>;
    reload(): Promise<void>;
    reloadMainThread(): Promise<void>;
    loadMore(): Promise<void>;
    getState(): ThreadListState;
    subscribe(callback: () => void): Unsubscribe;
    private _mainThreadListItemRuntime;
    readonly main: ThreadRuntime;
    get mainItem(): ThreadListItemRuntimeImpl;
    private _createItemStateBinding;
    getById(threadId: string): ThreadRuntime;
    getItemByIndex(idx: number): ThreadListItemRuntimeImpl;
    getArchivedItemByIndex(idx: number): ThreadListItemRuntimeImpl;
    getItemById(threadId: string): ThreadListItemRuntimeImpl;
}