import type { ThreadRuntime } from "../../runtime/api/thread-runtime.js";
import type { ClientOutput } from "@assistant-ui/store";
export declare const ThreadClient: import("@assistant-ui/tap").Resource<ClientOutput<"thread">, [{
    runtime: ThreadRuntime;
}]>;