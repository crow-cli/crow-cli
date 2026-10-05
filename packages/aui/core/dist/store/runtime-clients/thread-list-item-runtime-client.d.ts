import type { ClientOutput } from "@assistant-ui/store";
import type { ThreadListItemRuntime } from "../../runtime/api/thread-list-item-runtime.js";
export declare const ThreadListItemClient: import("@assistant-ui/tap").Resource<ClientOutput<"threadListItem">, [{
    runtime: ThreadListItemRuntime;
    mainThreadIsRunning?: boolean | undefined;
}]>;