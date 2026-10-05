import type { ExternalStoreThreadRuntimeCore } from "./external-store-thread-runtime-core.js";
import type { ThreadListItemCoreState, ThreadListRuntimeCore } from "../../runtime/interfaces/thread-list-runtime-core.js";
import type { ExternalStoreThreadListAdapter } from "./external-store-adapter.js";
import { BaseSubscribable } from "../../subscribable/subscribable.js";
export type ExternalStoreThreadFactory = () => ExternalStoreThreadRuntimeCore;
export declare class ExternalStoreThreadListRuntimeCore extends BaseSubscribable implements ThreadListRuntimeCore {
    private _mainThreadId;
    private _threads;
    private _archivedThreads;
    private _threadData;
    private adapter;
    get isLoading(): boolean;
    get newThreadId(): undefined;
    get threadIds(): readonly string[];
    get archivedThreadIds(): readonly string[];
    get threadItems(): Readonly<Record<string, ThreadListItemCoreState>>;
    getLoadThreadsPromise(): Promise<void>;
    private _mainThread;
    get mainThreadId(): string;
    private threadFactory;
    constructor(adapter: ExternalStoreThreadListAdapter | undefined, threadFactory: ExternalStoreThreadFactory);
    getMainThreadRuntimeCore(): ExternalStoreThreadRuntimeCore;
    getThreadRuntimeCore(): never;
    getItemById(threadId: string): ThreadListItemCoreState | undefined;
    __internal_setAdapter(adapter: ExternalStoreThreadListAdapter, initialLoad?: boolean): void;
    reloadMainThread(): Promise<void>;
    switchToThread(threadId: string, _options?: {
        unarchive?: boolean;
    }): Promise<void>;
    switchToNewThread(): Promise<void>;
    rename(threadId: string, newTitle: string): Promise<void>;
    updateCustom(threadId: string, custom: Record<string, unknown> | undefined): Promise<void>;
    detach(): Promise<void>;
    archive(threadId: string): Promise<void>;
    unarchive(threadId: string): Promise<void>;
    delete(threadId: string): Promise<void>;
    initialize(threadId: string): Promise<{
        remoteId: string;
        externalId: string | undefined;
    }>;
    generateTitle(): never;
}