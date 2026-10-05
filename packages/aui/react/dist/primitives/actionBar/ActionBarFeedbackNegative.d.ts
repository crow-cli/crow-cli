import type { ActionButtonProps } from "../../utils/createActionButton.js";
declare const useActionBarFeedbackNegative: () => () => void;
export declare namespace ActionBarPrimitiveFeedbackNegative {
    type Element = HTMLButtonElement;
    type Props = ActionButtonProps<typeof useActionBarFeedbackNegative>;
}
export declare const ActionBarPrimitiveFeedbackNegative: import("react").ForwardRefExoticComponent<Omit<Omit<import("react").ClassAttributes<HTMLButtonElement> & import("react").ButtonHTMLAttributes<HTMLButtonElement> & {
    asChild?: boolean;
}, "ref"> & {
    render?: import("react").ReactElement | undefined;
} & import("react").RefAttributes<HTMLButtonElement>, "ref"> & import("react").RefAttributes<HTMLButtonElement>>;
export {};