import { type ResourceElement } from "@assistant-ui/tap";
import type { ClientOutput } from "@assistant-ui/store";
import type { RuntimeAdapters } from "../../runtimes/remote-thread-list/types.js";
export declare const AdaptedRemoteThread: import("@assistant-ui/tap").Resource<ClientOutput<"thread">, [{
    useAdapters: () => RuntimeAdapters | null | undefined;
    thread: ResourceElement<ClientOutput<"thread">>;
}]>;