import type { Attachment } from "../../../types/attachment.js";
import { type ComponentType, type FC, type ReactNode } from "react";
type MessageAttachmentsComponentConfig = {
    Image?: ComponentType | undefined;
    Document?: ComponentType | undefined;
    File?: ComponentType | undefined;
    Attachment?: ComponentType | undefined;
};
export declare namespace MessagePrimitiveAttachments {
    type Props = {
        /** @deprecated Use the children render function instead. */
        components: MessageAttachmentsComponentConfig;
        children?: never;
    } | {
        /**
         * Render function called for each attachment. Receives the attachment,
         * which is still being prepared while the message is the composer's
         * submission.
         */
        children: (value: {
            attachment: Attachment;
        }) => ReactNode;
        components?: never;
    };
}
export declare namespace MessagePrimitiveAttachmentByIndex {
    type Props = {
        index: number;
        components?: MessageAttachmentsComponentConfig;
    };
}
/**
 * Renders a single attachment at the specified index within the current message.
 */
export declare const MessagePrimitiveAttachmentByIndex: FC<MessagePrimitiveAttachmentByIndex.Props>;
export declare const MessagePrimitiveAttachments: FC<MessagePrimitiveAttachments.Props>;
export {};