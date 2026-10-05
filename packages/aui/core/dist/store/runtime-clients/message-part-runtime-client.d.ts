import type { ClientOutput } from "@assistant-ui/store";
import type { MessagePartRuntime } from "../../runtime/api/message-part-runtime.js";
export declare const MessagePartClient: import("@assistant-ui/tap").Resource<ClientOutput<"part">, [{
    runtime: MessagePartRuntime;
}]>;