import { type ActionButtonElement, type ActionButtonProps } from "../../utils/createActionButton.js";
declare const useActionBarSpeak: () => (() => Promise<void>) | null;
export declare namespace ActionBarPrimitiveSpeak {
    type Element = ActionButtonElement;
    type Props = ActionButtonProps<typeof useActionBarSpeak>;
}
export declare const ActionBarPrimitiveSpeak: import("react").ForwardRefExoticComponent<Omit<Omit<import("react").ClassAttributes<HTMLButtonElement> & import("react").ButtonHTMLAttributes<HTMLButtonElement> & {
    asChild?: boolean;
}, "ref"> & {
    render?: import("react").ReactElement | undefined;
} & import("react").RefAttributes<HTMLButtonElement>, "ref"> & import("react").RefAttributes<HTMLButtonElement>>;
export {};