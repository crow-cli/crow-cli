import type { RemoteThreadInitializeResponse, RemoteThreadMetadata } from "./types.js";
export type RemoteThreadData = {
    readonly id: string;
    readonly remoteId: undefined;
    readonly externalId: undefined;
    readonly status: "new";
    readonly title: undefined;
    readonly custom: undefined;
    readonly localOrigin?: true;
} | {
    readonly id: string;
    readonly initializeTask: Promise<RemoteThreadInitializeResponse>;
    readonly remoteId: undefined;
    readonly externalId: undefined;
    readonly status: "regular" | "archived";
    readonly title?: string | undefined;
    readonly custom: undefined;
    readonly localOrigin?: true;
} | {
    readonly id: string;
    readonly initializeTask: Promise<RemoteThreadInitializeResponse>;
    readonly remoteId: string;
    readonly externalId: string | undefined;
    readonly status: "regular" | "archived";
    readonly title?: string | undefined;
    readonly lastMessageAt?: Date | undefined;
    readonly custom?: Record<string, unknown> | undefined;
    readonly localOrigin?: true;
};
export type THREAD_MAPPING_ID = string & {
    __brand: "THREAD_MAPPING_ID";
};
export declare function createThreadMappingId(id: string): THREAD_MAPPING_ID;
export declare const LOCAL_THREAD_ID_PREFIX = "__LOCALID_";
export declare const normalizeCursor: (c: string | undefined) => string | undefined;
export type ClassifyAccumulator = {
    threadIds: string[];
    archivedThreadIds: string[];
    threadIdMap: Record<string, THREAD_MAPPING_ID>;
    threadData: Record<THREAD_MAPPING_ID, RemoteThreadData>;
};
export declare const classifyThreads: (threads: readonly RemoteThreadMetadata[], acc: ClassifyAccumulator) => ClassifyAccumulator;
export type RemoteThreadState = {
    readonly isLoading: boolean;
    readonly loadError: unknown;
    readonly isLoadingMore: boolean;
    readonly cursor: string | undefined;
    readonly newThreadId: string | undefined;
    readonly threadIds: readonly string[];
    readonly archivedThreadIds: readonly string[];
    readonly threadIdMap: Readonly<Record<string, THREAD_MAPPING_ID>>;
    readonly threadData: Readonly<Record<THREAD_MAPPING_ID, RemoteThreadData>>;
};
export declare const createEmptyRemoteThreadState: () => RemoteThreadState;
export declare const seedNewThread: (state: RemoteThreadState, initialThreadIdSeed?: string) => {
    id: string;
    state: RemoteThreadState;
};
export declare const preserveMidLoadTransitions: (state: RemoteThreadState, priorOrder: Pick<RemoteThreadState, "threadIds" | "archivedThreadIds">, statusAtRequest: ReadonlyMap<string, RemoteThreadData["status"]>) => RemoteThreadState;
export declare const statusSnapshot: (state: RemoteThreadState) => ReadonlyMap<string, RemoteThreadData["status"]>;
export declare const getThreadData: (state: RemoteThreadState, threadIdOrRemoteId: string) => RemoteThreadData | undefined;
export declare const reconcileInitializedThread: (state: RemoteThreadState, threadId: string, remoteId: string, externalId: string | undefined, retainedThreadId?: string) => {
    state: RemoteThreadState;
    removedMappingId: THREAD_MAPPING_ID | undefined;
    survivorMappingId: THREAD_MAPPING_ID;
};
/**
 * Transitions a thread that already exists remotely. Promoting the local draft
 * off `new` needs the initialization promise its destination variant requires,
 * so that goes through `promoteNewThreadReducer`; asking for it here leaves the
 * state unchanged.
 */
export declare const updateStatusReducer: (state: RemoteThreadState, threadIdOrRemoteId: string, newStatus: "regular" | "archived" | "deleted") => RemoteThreadState;
/**
 * Promotes the local draft to `regular`, carrying the initialization promise
 * onto the slot.
 */
export declare const promoteNewThreadReducer: (state: RemoteThreadState, threadIdOrRemoteId: string, initializeTask: Promise<RemoteThreadInitializeResponse>) => RemoteThreadState;