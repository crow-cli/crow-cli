import { type ActionButtonElement, type ActionButtonProps } from "../../utils/createActionButton.js";
declare const useThreadSuggestion: ({ prompt, send, clearComposer, autoSend, method: _method, }: {
    /** The suggestion prompt. */
    prompt: string;
    /**
     * When true, automatically sends the message.
     * When false, replaces or appends the composer text with the suggestion - depending on the value of `clearComposer`.
     */
    send?: boolean | undefined;
    /**
     * Whether to clear the composer after sending. A send queued while a run is
     * in progress never clears the composer.
     * When send is set to false, determines if composer text is replaced with suggestion (true, default),
     * or if it's appended to the composer text (false).
     *
     * @default true
     */
    clearComposer?: boolean | undefined;
    /** @deprecated Use `send` instead. */
    autoSend?: boolean | undefined;
    /** @deprecated Use `clearComposer` instead. */
    method?: "replace";
}) => (() => void) | null;
export declare namespace ThreadPrimitiveSuggestion {
    type Element = ActionButtonElement;
    type Props = ActionButtonProps<typeof useThreadSuggestion>;
}
export declare const ThreadPrimitiveSuggestion: import("react").ForwardRefExoticComponent<Omit<Omit<import("react").ClassAttributes<HTMLButtonElement> & import("react").ButtonHTMLAttributes<HTMLButtonElement> & {
    asChild?: boolean;
}, "ref"> & {
    render?: import("react").ReactElement | undefined;
} & import("react").RefAttributes<HTMLButtonElement>, "ref"> & {
    /** The suggestion prompt. */
    prompt: string;
    /**
     * When true, automatically sends the message.
     * When false, replaces or appends the composer text with the suggestion - depending on the value of `clearComposer`.
     */
    send?: boolean | undefined;
    /**
     * Whether to clear the composer after sending. A send queued while a run is
     * in progress never clears the composer.
     * When send is set to false, determines if composer text is replaced with suggestion (true, default),
     * or if it's appended to the composer text (false).
     *
     * @default true
     */
    clearComposer?: boolean | undefined;
    /** @deprecated Use `send` instead. */
    autoSend?: boolean | undefined;
    /** @deprecated Use `clearComposer` instead. */
    method?: "replace";
} & import("react").RefAttributes<HTMLButtonElement>>;
export {};