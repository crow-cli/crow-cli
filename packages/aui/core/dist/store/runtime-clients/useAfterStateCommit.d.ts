/**
 * Delays a promise until the client has committed a render of the source
 * state current at settlement, so a caller awaiting it reads the result from
 * the client's `getState()`. A promise that settles before the first commit
 * waits for it. The wait ends after `COMMIT_TIMEOUT_MS`, and at once after
 * unmount. Each source promise maps to one delayed promise, keeping it stable
 * for `use()` and Suspense caches. `getLatestState` must be stable.
 */
export declare const useAfterStateCommit: <TState>(renderedState: TState, getLatestState: () => TState) => <T>(promise: Promise<T>) => Promise<T>;