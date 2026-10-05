import type { ExternalStoreAdapter } from "../../runtimes/external-store/external-store-adapter.js";
import type { AssistantRuntime } from "../../runtime/api/assistant-runtime.js";
export declare const useExternalStoreRuntime: <T>(store: ExternalStoreAdapter<T>) => AssistantRuntime;