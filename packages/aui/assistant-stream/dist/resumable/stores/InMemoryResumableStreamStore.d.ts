import type { ResumableStreamStore } from "../types.js";
export type InMemoryResumableStreamStoreOptions = {
    readonly defaultTtlMs?: number;
    readonly now?: () => number;
    readonly maxChunkBytes?: number;
    readonly maxEntriesPerStream?: number;
    readonly maxStreams?: number;
    readonly gcIntervalMs?: number;
};
export declare function createInMemoryResumableStreamStore(options?: InMemoryResumableStreamStoreOptions): ResumableStreamStore & {
    dispose: () => void;
};