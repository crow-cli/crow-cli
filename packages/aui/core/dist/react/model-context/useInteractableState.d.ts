type StateUpdater<TState> = TState | ((prev: TState) => TState);
/**
 * Reads and writes the state of an interactable registered elsewhere, by id.
 *
 * Use this from secondary readers (children, siblings); the owning component
 * registers with `unstable_useInteractable`, which returns state directly. Returns
 * `undefined` until the owning interactable is registered.
 *
 * @deprecated Unstable / Experimental (not actually removed).
 */
export declare const unstable_useInteractableState: <TState>(id: string) => [
    TState | undefined,
    {
        setState: (updater: StateUpdater<TState>) => void;
        isPending: boolean;
        error: unknown;
        flush: () => Promise<void>;
    }
];
export {};