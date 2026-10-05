import { useConfiguredAui } from "@assistant-ui/store/client";
import type { AssistantRuntime } from "../../runtime/api/assistant-runtime.js";
import type { ThreadListRuntimeCore } from "../../runtime/interfaces/thread-list-runtime-core.js";
import type { ThreadRuntimeCore } from "../../runtime/interfaces/thread-runtime-core.js";
import { type ThreadListItemRuntime } from "../../runtime/api/thread-list-item-runtime.js";
import { type RuntimeAdapters } from "./RuntimeAdapterProvider.js";
export type RemoteThreadListHook = () => AssistantRuntime;
export type RemoteThreadResourceProps = {
    threadId: string;
    generation: number;
    parentList: ThreadListRuntimeCore;
    runtimeHook: RemoteThreadListHook;
    parentClient: Parameters<typeof useConfiguredAui>[0];
    adapters: RuntimeAdapters | null;
    publish: (threadId: string, runtime: ThreadRuntimeCore, generation: number) => void;
    destroySignal: AbortSignal;
};
export declare const subscribeToTitleGeneration: (threadRuntime: AssistantRuntime["thread"], itemRuntime: ThreadListItemRuntime) => import("../../index.js").Unsubscribe;
export declare const RemoteThreadResource: import("@assistant-ui/tap").Resource<AssistantRuntime, [RemoteThreadResourceProps]>;