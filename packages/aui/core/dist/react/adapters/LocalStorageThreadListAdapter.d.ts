import { useAui } from "@assistant-ui/store";
import type { RemoteThreadListAdapter, ThreadHistoryAdapter } from "../../index.js";
import type { ExportedMessageRepository } from "../../internal.js";
import type { TitleGenerationAdapter } from "./TitleGenerationAdapter.js";
export type AsyncStorageLike = {
    getItem(key: string): Promise<string | null>;
    setItem(key: string, value: string): Promise<void>;
    removeItem(key: string): Promise<void>;
};
declare class KeyedMutationQueue {
    private readonly tails;
    private readonly staleKeys;
    markStale(key: string): void;
    removeStale(key: string, storage: AsyncStorageLike): Promise<void>;
    run<T>(key: string, mutation: () => Promise<T>): Promise<T>;
}
type LocalStorageAdapterOptions = {
    storage: AsyncStorageLike;
    prefix?: string | undefined;
    titleGenerator?: TitleGenerationAdapter | undefined;
};
type StoredThreadMetadata = {
    remoteId: string;
    externalId?: string;
    status: "regular" | "archived";
    title?: string;
    custom?: Record<string, unknown> | undefined;
};
export declare const parseStoredThreadMetadata: (raw: string | null) => StoredThreadMetadata[];
export declare const parseStoredMessageRepository: (raw: string | null) => ExportedMessageRepository;
export declare const createLocalStorageHistoryAdapter: (storage: AsyncStorageLike, getAui: () => ReturnType<typeof useAui>, prefix: string, mutationQueue?: KeyedMutationQueue) => ThreadHistoryAdapter;
export declare const createLocalStorageAdapter: (options: LocalStorageAdapterOptions) => RemoteThreadListAdapter;
export {};