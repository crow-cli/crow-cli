import type { ActionButtonElement, ActionButtonProps } from "../../utils/createActionButton.js";
export declare namespace ThreadListPrimitiveNew {
    type Element = ActionButtonElement;
    type Props = ActionButtonProps<() => void>;
}
export declare const ThreadListPrimitiveNew: import("react").ForwardRefExoticComponent<Omit<Omit<import("react").ClassAttributes<HTMLButtonElement> & import("react").ButtonHTMLAttributes<HTMLButtonElement> & {
    asChild?: boolean;
}, "ref"> & {
    render?: import("react").ReactElement | undefined;
} & import("react").RefAttributes<HTMLButtonElement>, "ref"> & import("react").RefAttributes<HTMLButtonElement>>;