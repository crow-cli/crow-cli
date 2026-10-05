import { type ActionButtonElement, type ActionButtonProps } from "../../utils/createActionButton.js";
export declare namespace useThreadScrollToBottom {
    type Options = {
        behavior?: ScrollBehavior | undefined;
    };
}
declare const useThreadScrollToBottom: ({ behavior, }?: useThreadScrollToBottom.Options) => (() => void) | null;
export declare namespace ThreadPrimitiveScrollToBottom {
    type Element = ActionButtonElement;
    type Props = ActionButtonProps<typeof useThreadScrollToBottom>;
}
export declare const ThreadPrimitiveScrollToBottom: import("react").ForwardRefExoticComponent<Omit<Omit<import("react").ClassAttributes<HTMLButtonElement> & import("react").ButtonHTMLAttributes<HTMLButtonElement> & {
    asChild?: boolean;
}, "ref"> & {
    render?: import("react").ReactElement | undefined;
} & import("react").RefAttributes<HTMLButtonElement>, "ref"> & useThreadScrollToBottom.Options & import("react").RefAttributes<HTMLButtonElement>>;
export {};