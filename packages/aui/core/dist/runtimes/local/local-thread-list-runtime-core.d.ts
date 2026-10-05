import type { ThreadListRuntimeCore } from "../../runtime/interfaces/thread-list-runtime-core.js";
import { BaseSubscribable } from "../../subscribable/subscribable.js";
import type { LocalThreadRuntimeCore } from "./local-thread-runtime-core.js";
export type LocalThreadFactory = () => LocalThreadRuntimeCore;
export declare class LocalThreadListRuntimeCore extends BaseSubscribable implements ThreadListRuntimeCore {
    private _mainThread;
    constructor(_threadFactory: LocalThreadFactory);
    get isLoading(): boolean;
    getMainThreadRuntimeCore(): LocalThreadRuntimeCore;
    get newThreadId(): string | undefined;
    get threadIds(): readonly string[];
    get archivedThreadIds(): readonly string[];
    get mainThreadId(): string;
    get threadItems(): Readonly<{
        __DEFAULT_ID__: {
            id: string;
            remoteId: undefined;
            externalId: undefined;
            status: "regular";
            title: undefined;
        };
    }>;
    getThreadRuntimeCore(): never;
    getLoadThreadsPromise(): Promise<void>;
    getItemById(threadId: string): {
        status: "regular";
        id: string;
        remoteId: string;
        externalId: undefined;
        title: undefined;
        isMain: boolean;
    };
    switchToThread(): Promise<void>;
    switchToNewThread(): Promise<void>;
    rename(): Promise<void>;
    archive(): Promise<void>;
    detach(): Promise<void>;
    unarchive(): Promise<void>;
    delete(): Promise<void>;
    initialize(threadId: string): Promise<{
        remoteId: string;
        externalId: string | undefined;
    }>;
    generateTitle(): never;
}