import { type ActionButtonElement, type ActionButtonProps } from "../../utils/createActionButton.js";
declare const useComposerAddAttachment: ({ multiple, }?: {
    /** allow selecting multiple files */
    multiple?: boolean | undefined;
}) => (() => void) | null;
export declare namespace ComposerPrimitiveAddAttachment {
    type Element = ActionButtonElement;
    type Props = ActionButtonProps<typeof useComposerAddAttachment>;
}
export declare const ComposerPrimitiveAddAttachment: import("react").ForwardRefExoticComponent<Omit<Omit<import("react").ClassAttributes<HTMLButtonElement> & import("react").ButtonHTMLAttributes<HTMLButtonElement> & {
    asChild?: boolean;
}, "ref"> & {
    render?: import("react").ReactElement | undefined;
} & import("react").RefAttributes<HTMLButtonElement>, "ref"> & {
    /** allow selecting multiple files */
    multiple?: boolean | undefined;
} & import("react").RefAttributes<HTMLButtonElement>>;
export {};