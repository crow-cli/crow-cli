import type { Unsubscribe } from "@assistant-ui/core";
import type { AssistantClient } from "@assistant-ui/store";
export interface EventLog {
    time: Date;
    event: string;
    data: unknown;
}
interface DevToolsApiEntry {
    api: Partial<AssistantClient>;
    logs: EventLog[];
}
interface DevToolsHook {
    apis: Map<number, DevToolsApiEntry>;
    nextId: number;
    listeners: Set<(apiId: number) => void>;
}
declare global {
    interface Window {
        __ASSISTANT_UI_DEVTOOLS_HOOK__?: DevToolsHook;
    }
}
export declare class DevToolsHooks {
    static subscribe(listener: () => void): Unsubscribe;
    static clearEventLogs(apiId: number): void;
    static getApis(): Map<number, DevToolsApiEntry>;
}
export declare class DevToolsProviderApi {
    private static readonly MAX_EVENT_LOGS_PER_API;
    static register(aui: Partial<AssistantClient>): Unsubscribe;
}
export {};