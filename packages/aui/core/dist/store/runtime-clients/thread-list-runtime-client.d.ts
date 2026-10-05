import type { ClientOutput } from "@assistant-ui/store";
import type { ThreadListRuntime } from "../../runtime/api/thread-list-runtime.js";
import type { AssistantRuntime } from "../../runtime/api/assistant-runtime.js";
export declare const ThreadListClient: import("@assistant-ui/tap").Resource<ClientOutput<"threads">, [{
    runtime: ThreadListRuntime;
    __internal_assistantRuntime: AssistantRuntime;
}]>;