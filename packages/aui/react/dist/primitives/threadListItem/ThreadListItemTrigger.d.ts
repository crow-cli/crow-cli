import { type ActionButtonElement, type ActionButtonProps } from "../../utils/createActionButton.js";
declare const useThreadListItemTrigger: () => () => void;
export declare namespace ThreadListItemPrimitiveTrigger {
    type Element = ActionButtonElement;
    type Props = ActionButtonProps<typeof useThreadListItemTrigger>;
}
export declare const ThreadListItemPrimitiveTrigger: import("react").ForwardRefExoticComponent<Omit<Omit<import("react").ClassAttributes<HTMLButtonElement> & import("react").ButtonHTMLAttributes<HTMLButtonElement> & {
    asChild?: boolean;
}, "ref"> & {
    render?: import("react").ReactElement | undefined;
} & import("react").RefAttributes<HTMLButtonElement>, "ref"> & import("react").RefAttributes<HTMLButtonElement>>;
export {};