import type { FC } from "react";
import { MessagePrimitiveParts as MessagePrimitivePartsBase, MessagePartComponent as MessagePartComponentBase, MessagePrimitivePartByIndex as MessagePrimitivePartByIndexBase } from "@assistant-ui/core/react";
export declare namespace MessagePrimitiveParts {
    type Props = MessagePrimitivePartsBase.Props;
}
/**
 * Renders the parts of a message with web-specific default components.
 */
export declare const MessagePrimitiveParts: FC<MessagePrimitiveParts.Props>;
export { MessagePartComponentBase as MessagePartComponent, MessagePrimitivePartByIndexBase as MessagePrimitivePartByIndex, };