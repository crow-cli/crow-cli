import { type ComponentType, type FC, type ReactNode } from "react";
import type { MessageState } from "../../../store/index.js";
type MessagesComponentConfig = {
    /** Component used to render all message types */
    Message: ComponentType;
    /** Component used when editing any message type */
    EditComposer?: ComponentType | undefined;
    /** Component used when editing user messages specifically */
    UserEditComposer?: ComponentType | undefined;
    /** Component used when editing assistant messages specifically */
    AssistantEditComposer?: ComponentType | undefined;
    /** Component used when editing system messages specifically */
    SystemEditComposer?: ComponentType | undefined;
    /** Component used to render user messages specifically */
    UserMessage?: ComponentType | undefined;
    /** Component used to render assistant messages specifically */
    AssistantMessage?: ComponentType | undefined;
    /** Component used to render system messages specifically */
    SystemMessage?: ComponentType | undefined;
} | {
    /** Component used to render all message types (fallback) */
    Message?: ComponentType | undefined;
    /** Component used when editing any message type */
    EditComposer?: ComponentType | undefined;
    /** Component used when editing user messages specifically */
    UserEditComposer?: ComponentType | undefined;
    /** Component used when editing assistant messages specifically */
    AssistantEditComposer?: ComponentType | undefined;
    /** Component used when editing system messages specifically */
    SystemEditComposer?: ComponentType | undefined;
    /** Component used to render user messages */
    UserMessage: ComponentType;
    /** Component used to render assistant messages */
    AssistantMessage: ComponentType;
    /** Component used to render system messages */
    SystemMessage?: ComponentType | undefined;
};
export declare namespace ThreadPrimitiveMessages {
    type Props = {
        /** @deprecated Use the children render function instead. */
        components: MessagesComponentConfig;
        children?: never;
    } | {
        /** Render function called for each message. Receives the message. */
        children: (value: {
            message: MessageState;
        }) => ReactNode;
        components?: never;
    };
}
export declare namespace ThreadPrimitiveMessageByIndex {
    type Props = {
        index: number;
        components: MessagesComponentConfig;
    };
}
/**
 * Renders a single message at the specified index in the current thread.
 */
export declare const ThreadPrimitiveMessageByIndex: FC<ThreadPrimitiveMessageByIndex.Props>;
export declare namespace ThreadPrimitiveUnstable_MessageById {
    type Props = {
        messageId: string;
        components: MessagesComponentConfig;
    };
}
/**
 * Renders the message with the given id in the current thread.
 *
 * Unlike {@link ThreadPrimitiveMessageByIndex}, this keys off the message id,
 * so it stays attached to the same message across reordering and windowing -
 * the shape needed to drive a virtualized or custom message list together with
 * `unstable_useThreadMessageIds`. A missing or removed id renders `null` rather
 * than throwing.
 *
 * @deprecated Unstable / Experimental - may change in any release.
 *
 * @example
 * ```tsx
 * const messageIds = unstable_useThreadMessageIds();
 * return messageIds.map((messageId) => (
 *   <ThreadPrimitive.Unstable_MessageById
 *     key={messageId}
 *     messageId={messageId}
 *     components={MESSAGE_COMPONENTS}
 *   />
 * ));
 * ```
 */
export declare const ThreadPrimitiveUnstable_MessageById: FC<ThreadPrimitiveUnstable_MessageById.Props>;
/**
 * Renders all messages in the current thread.
 *
 * @example
 * ```tsx
 * <ThreadPrimitive.Messages>
 *   {({ message }) => {
 *     if (message.role === "user") return <MyUserMessage />;
 *     return <MyAssistantMessage />;
 *   }}
 * </ThreadPrimitive.Messages>
 * ```
 */
export declare const ThreadPrimitiveMessagesImpl: FC<ThreadPrimitiveMessages.Props>;
export declare const ThreadPrimitiveMessages: import("react").NamedExoticComponent<ThreadPrimitiveMessages.Props>;
export {};