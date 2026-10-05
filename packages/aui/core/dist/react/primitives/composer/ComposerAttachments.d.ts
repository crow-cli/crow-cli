import type { Attachment } from "../../../types/attachment.js";
import { type ComponentType, type FC, type ReactNode } from "react";
type ComposerAttachmentsComponentConfig = {
    Image?: ComponentType | undefined;
    Document?: ComponentType | undefined;
    File?: ComponentType | undefined;
    Attachment?: ComponentType | undefined;
};
export declare namespace ComposerPrimitiveAttachments {
    type Props = {
        /** @deprecated Use the children render function instead. */
        components: ComposerAttachmentsComponentConfig;
        children?: never;
    } | {
        /** Render function called for each attachment. Receives the attachment. */
        children: (value: {
            attachment: Attachment;
        }) => ReactNode;
        components?: never;
    };
}
export declare namespace ComposerPrimitiveAttachmentByIndex {
    type Props = {
        index: number;
        components?: ComposerAttachmentsComponentConfig;
    };
}
/**
 * Renders a single attachment at the specified index within the composer.
 */
export declare const ComposerPrimitiveAttachmentByIndex: FC<ComposerPrimitiveAttachmentByIndex.Props>;
export declare const ComposerPrimitiveAttachments: FC<ComposerPrimitiveAttachments.Props>;
export {};