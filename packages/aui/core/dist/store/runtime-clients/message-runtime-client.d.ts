import type { ClientOutput } from "@assistant-ui/store";
import type { MessageRuntime } from "../../runtime/api/message-runtime.js";
export declare const MessageClient: import("@assistant-ui/tap").Resource<ClientOutput<"message">, [{
    runtime: MessageRuntime;
    threadIdRef: {
        current: string;
    };
    threadId: string;
    /** False when the thread renders a message the runtime does not hold after this one. */
    isLast?: false | undefined;
}]>;