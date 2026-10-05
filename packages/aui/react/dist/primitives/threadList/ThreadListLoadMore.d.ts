import { type ActionButtonElement, type ActionButtonProps } from "../../utils/createActionButton.js";
declare const useThreadListLoadMore: () => (() => void) | null;
export declare namespace ThreadListPrimitiveLoadMore {
    type Element = ActionButtonElement;
    type Props = ActionButtonProps<typeof useThreadListLoadMore>;
}
export declare const ThreadListPrimitiveLoadMore: import("react").ForwardRefExoticComponent<Omit<Omit<import("react").ClassAttributes<HTMLButtonElement> & import("react").ButtonHTMLAttributes<HTMLButtonElement> & {
    asChild?: boolean;
}, "ref"> & {
    render?: import("react").ReactElement | undefined;
} & import("react").RefAttributes<HTMLButtonElement>, "ref"> & import("react").RefAttributes<HTMLButtonElement>>;
export {};