import { type ActionButtonElement, type ActionButtonProps } from "../../utils/createActionButton.js";
declare const useAttachmentRemove: () => () => void;
export declare namespace AttachmentPrimitiveRemove {
    type Element = ActionButtonElement;
    type Props = ActionButtonProps<typeof useAttachmentRemove>;
}
export declare const AttachmentPrimitiveRemove: import("react").ForwardRefExoticComponent<Omit<Omit<import("react").ClassAttributes<HTMLButtonElement> & import("react").ButtonHTMLAttributes<HTMLButtonElement> & {
    asChild?: boolean;
}, "ref"> & {
    render?: import("react").ReactElement | undefined;
} & import("react").RefAttributes<HTMLButtonElement>, "ref"> & import("react").RefAttributes<HTMLButtonElement>>;
export {};