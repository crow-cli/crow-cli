import { type ReactElement } from "react";
import type React from "react";
export declare namespace ComposerPrimitiveAttachmentDropzone {
    type Element = HTMLDivElement;
    type Props = React.HTMLAttributes<HTMLDivElement> & {
        asChild?: boolean | undefined;
        render?: ReactElement | undefined;
        disabled?: boolean | undefined;
    };
}
export declare const ComposerPrimitiveAttachmentDropzone: React.ForwardRefExoticComponent<React.HTMLAttributes<HTMLDivElement> & {
    asChild?: boolean | undefined;
    render?: ReactElement | undefined;
    disabled?: boolean | undefined;
} & React.RefAttributes<HTMLDivElement>>;