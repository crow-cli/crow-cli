import { type ActionButtonElement, type ActionButtonProps } from "../../utils/createActionButton.js";
declare const useThreadListItemDelete: () => () => void;
export declare namespace ThreadListItemPrimitiveDelete {
    type Element = ActionButtonElement;
    type Props = ActionButtonProps<typeof useThreadListItemDelete>;
}
export declare const ThreadListItemPrimitiveDelete: import("react").ForwardRefExoticComponent<Omit<Omit<import("react").ClassAttributes<HTMLButtonElement> & import("react").ButtonHTMLAttributes<HTMLButtonElement> & {
    asChild?: boolean;
}, "ref"> & {
    render?: import("react").ReactElement | undefined;
} & import("react").RefAttributes<HTMLButtonElement>, "ref"> & import("react").RefAttributes<HTMLButtonElement>>;
export {};