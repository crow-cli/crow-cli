type StateUpdater<TState> = TState | ((prev: TState) => TState);
/**
 * Reads and writes the state of a registered interactable.
 *
 * Pair with {@link useAssistantInteractable} which handles registration.
 *
 * @deprecated Since 2026-06-14 — migrate to the Unstable / Experimental API.
 * Scheduled for removal on/after 2026-09-14. See
 * {@link https://www.assistant-ui.com/docs/tools/interactables#migrating-from-the-previous-api | Interactables migration guide}.
 */
export declare const useInteractableState: <TState>(id: string, fallback: TState) => [TState, {
    setState: (updater: StateUpdater<TState>) => void;
    setSelected: (selected: boolean) => void;
    isPending: boolean;
    error: unknown;
    flush: () => Promise<void>;
}];
export {};