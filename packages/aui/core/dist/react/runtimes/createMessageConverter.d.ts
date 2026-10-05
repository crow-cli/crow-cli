import type { ThreadMessage } from "../../types/message.js";
import type { ThreadRuntimeState } from "../../runtime/api/thread-runtime.js";
import { useExternalMessageConverter, type JoinStrategy } from "./external-message-converter.js";
export declare const createMessageConverter: <T extends object>(callback: useExternalMessageConverter.Callback<T>) => {
    useThreadMessages: ({ messages, isRunning, joinStrategy, metadata, }: {
        messages: T[];
        isRunning: boolean;
        joinStrategy?: JoinStrategy | undefined;
        metadata?: useExternalMessageConverter.Metadata;
    }) => ThreadMessage[];
    toThreadMessages: (messages: T[], isRunning?: boolean, metadata?: useExternalMessageConverter.Metadata) => ThreadMessage[];
    toOriginalMessages: (input: ThreadRuntimeState | ThreadMessage | ThreadMessage["content"][number]) => unknown[];
    toOriginalMessage: (input: ThreadRuntimeState | ThreadMessage | ThreadMessage["content"][number]) => {};
    useOriginalMessage: () => {};
    useOriginalMessages: () => unknown[];
};