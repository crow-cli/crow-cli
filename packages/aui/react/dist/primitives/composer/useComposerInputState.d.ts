export type TriggerPopoverAriaProps = {
    "aria-controls"?: string;
    "aria-expanded"?: true;
    "aria-haspopup"?: "listbox";
    "aria-activedescendant"?: string | undefined;
};
export declare function useComposerInputValue(): string;
export declare function useComposerInputDisabled(disabled?: boolean | undefined): boolean;
export declare function useTriggerPopoverAriaProps(): TriggerPopoverAriaProps;