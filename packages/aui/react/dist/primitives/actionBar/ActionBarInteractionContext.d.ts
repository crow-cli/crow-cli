export type ActionBarInteractionContextValue = {
    acquireInteractionLock: () => () => void;
};
export declare const ActionBarInteractionContext: import("react").Context<ActionBarInteractionContextValue | null>;
export declare const useActionBarInteractionContext: () => ActionBarInteractionContextValue | null;