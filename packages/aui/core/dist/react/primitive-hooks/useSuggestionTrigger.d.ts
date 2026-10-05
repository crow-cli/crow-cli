export type UseSuggestionTriggerOptions = {
    prompt: string;
    send?: boolean | undefined;
    clearComposer?: boolean | undefined;
};
export declare const useSuggestionTrigger: ({ prompt, send, clearComposer, }: UseSuggestionTriggerOptions) => {
    trigger: () => void;
    disabled: boolean;
};