export declare const DestroySignalContext: import("react").Context<AbortSignal | undefined>;
/**
 * Scopes a subtree to the permanent teardown of whatever owns it. The signal
 * aborts when the owner is destroyed for good, never when a resource soft
 * unmounts and may come back, so a consumer may release work on it without
 * losing state a later reveal still needs. A caller with no owner of its own
 * passes `undefined` and the enclosing owner keeps standing.
 */
export declare const useDestroySignalProvider: <TResult>(destroySignal: AbortSignal | undefined, fn: () => TResult) => TResult;
/**
 * Returns the permanent teardown signal of the owner the caller runs under.
 * A caller outside any owned subtree resolves none, which retains its
 * resources rather than releasing them early.
 */
export declare const useAssistantClientDestroySignal: () => AbortSignal | undefined;