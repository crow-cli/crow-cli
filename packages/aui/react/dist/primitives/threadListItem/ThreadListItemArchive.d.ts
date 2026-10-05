import { type ActionButtonElement, type ActionButtonProps } from "../../utils/createActionButton.js";
declare const useThreadListItemArchive: () => () => void;
export declare namespace ThreadListItemPrimitiveArchive {
    type Element = ActionButtonElement;
    type Props = ActionButtonProps<typeof useThreadListItemArchive>;
}
export declare const ThreadListItemPrimitiveArchive: import("react").ForwardRefExoticComponent<Omit<Omit<import("react").ClassAttributes<HTMLButtonElement> & import("react").ButtonHTMLAttributes<HTMLButtonElement> & {
    asChild?: boolean;
}, "ref"> & {
    render?: import("react").ReactElement | undefined;
} & import("react").RefAttributes<HTMLButtonElement>, "ref"> & import("react").RefAttributes<HTMLButtonElement>>;
export {};