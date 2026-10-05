export type ComposerCompactContextValue = {
    setMultiline: (multiline: boolean) => void;
};
export declare const ComposerCompactContext: import("react").Context<ComposerCompactContextValue | null>;
export declare const useComposerCompactContextOptional: () => ComposerCompactContextValue | null;