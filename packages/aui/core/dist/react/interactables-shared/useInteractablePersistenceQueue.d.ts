import { type RefObject } from "react";
export declare const PERSISTENCE_DEBOUNCE_MS = 500;
/**
 * `load` is caller code with no settling contract, so an awaited `flush` bounds
 * the wait rather than inheriting it. Past this the edit stays queued for the
 * next successful snapshot, which is the same shape a failed load already has.
 */
export declare const FLUSH_LOAD_TIMEOUT_MS = 5000;
type PersistenceAdapter<State> = {
    save(state: State): void | Promise<void>;
};
type PersistenceStatus = {
    isPending: boolean;
    error: unknown;
};
type PersistenceStatusMap = Record<string, PersistenceStatus>;
type PersistenceStatusUpdater = (updater: (prev: PersistenceStatusMap) => PersistenceStatusMap) => void;
type UseInteractablePersistenceQueueOptions<State> = {
    adapterRef: RefObject<PersistenceAdapter<State> | undefined>;
    adapterGenerationRef: RefObject<number>;
    snapshot: () => State;
    updatePersistenceStatus: PersistenceStatusUpdater;
    retainDirtyWithoutAdapter?: boolean;
};
export declare const useInteractablePersistenceQueue: <State>({ adapterRef, adapterGenerationRef, snapshot, updatePersistenceStatus, retainDirtyWithoutAdapter, }: UseInteractablePersistenceQueueOptions<State>) => {
    discardPending: () => void;
    flushIfPending: () => void;
    getDirtyIds: () => Set<string>;
    schedulePersistence: (id: string) => void;
    flush: () => Promise<void>;
};
export {};