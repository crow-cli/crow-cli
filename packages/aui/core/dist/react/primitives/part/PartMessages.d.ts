import { type FC, type ReactNode } from "react";
import type { ThreadMessage } from "../../../types/message.js";
import { type ThreadPrimitiveMessages } from "../thread/ThreadMessages.js";
export declare namespace PartPrimitiveMessages {
    type Props = {
        components: NonNullable<ThreadPrimitiveMessages.Props["components"]>;
        children?: never;
    } | {
        /** Render function called for each message. Receives the message. */
        children: (value: {
            message: ThreadMessage;
        }) => ReactNode;
        components?: never;
    };
}
/**
 * Renders the nested messages of a tool call part (e.g. sub-agent conversation).
 *
 * This primitive reads `messages` from the current tool call part in the PartScope
 * and renders them using a readonly thread context. All existing message and part
 * primitives work inside, and parent tool UI registrations are inherited.
 * The nested thread reports `isRunning` while its trailing assistant message is running.
 *
 * @example
 * ```tsx
 * const toolkit = defineToolkit({
 *   invoke_sub_agent: {
 *     type: "backend",
 *     render: () => (
 *       <PartPrimitive.Messages>
 *         {({ message }) => {
 *           if (message.role === "user") return <MyUserMessage />;
 *           return <MyAssistantMessage />;
 *         }}
 *       </PartPrimitive.Messages>
 *     ),
 *   },
 * });
 * ```
 */
export declare const PartPrimitiveMessagesImpl: FC<PartPrimitiveMessages.Props>;
export declare const PartPrimitiveMessages: import("react").NamedExoticComponent<PartPrimitiveMessages.Props>;