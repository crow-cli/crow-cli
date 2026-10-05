import type { AssistantCloud } from "assistant-cloud";
import type { AssistantRuntime } from "../../../runtime/api/assistant-runtime.js";
type ThreadData = {
    externalId: string;
};
type CloudThreadListAdapter = {
    cloud: AssistantCloud;
    runtimeHook: () => AssistantRuntime;
    create?(threadId: string): Promise<ThreadData>;
    delete?(threadId: string): Promise<void>;
};
export declare function useCloudThreadListRuntime({ runtimeHook, ...adapterOptions }: CloudThreadListAdapter): AssistantRuntime;
export {};