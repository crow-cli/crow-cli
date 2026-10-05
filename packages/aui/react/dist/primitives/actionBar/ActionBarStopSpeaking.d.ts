import type { ActionButtonProps } from "../../utils/createActionButton.js";
declare const useActionBarStopSpeaking: () => (() => void) | null;
export declare namespace ActionBarPrimitiveStopSpeaking {
    type Element = HTMLButtonElement;
    type Props = ActionButtonProps<typeof useActionBarStopSpeaking>;
}
export declare const ActionBarPrimitiveStopSpeaking: import("react").ForwardRefExoticComponent<Omit<Omit<import("react").ClassAttributes<HTMLButtonElement> & import("react").ButtonHTMLAttributes<HTMLButtonElement> & {
    asChild?: boolean;
}, "ref"> & {
    render?: import("react").ReactElement | undefined;
} & import("react").RefAttributes<HTMLButtonElement>, "ref"> & import("react").RefAttributes<HTMLButtonElement>>;
export {};