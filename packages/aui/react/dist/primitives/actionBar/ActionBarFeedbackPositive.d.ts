import type { ActionButtonProps } from "../../utils/createActionButton.js";
declare const useActionBarFeedbackPositive: () => () => void;
export declare namespace ActionBarPrimitiveFeedbackPositive {
    type Element = HTMLButtonElement;
    type Props = ActionButtonProps<typeof useActionBarFeedbackPositive>;
}
export declare const ActionBarPrimitiveFeedbackPositive: import("react").ForwardRefExoticComponent<Omit<Omit<import("react").ClassAttributes<HTMLButtonElement> & import("react").ButtonHTMLAttributes<HTMLButtonElement> & {
    asChild?: boolean;
}, "ref"> & {
    render?: import("react").ReactElement | undefined;
} & import("react").RefAttributes<HTMLButtonElement>, "ref"> & import("react").RefAttributes<HTMLButtonElement>>;
export {};