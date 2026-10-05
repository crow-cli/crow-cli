import { type ActionButtonElement, type ActionButtonProps } from "../../utils/createActionButton.js";
declare const useThreadListItemUnarchive: () => () => void;
export declare namespace ThreadListItemPrimitiveUnarchive {
    type Element = ActionButtonElement;
    type Props = ActionButtonProps<typeof useThreadListItemUnarchive>;
}
export declare const ThreadListItemPrimitiveUnarchive: import("react").ForwardRefExoticComponent<Omit<Omit<import("react").ClassAttributes<HTMLButtonElement> & import("react").ButtonHTMLAttributes<HTMLButtonElement> & {
    asChild?: boolean;
}, "ref"> & {
    render?: import("react").ReactElement | undefined;
} & import("react").RefAttributes<HTMLButtonElement>, "ref"> & import("react").RefAttributes<HTMLButtonElement>>;
export {};