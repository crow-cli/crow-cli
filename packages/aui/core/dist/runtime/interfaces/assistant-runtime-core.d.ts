import type { Unsubscribe } from "../../types/unsubscribe.js";
import type { ModelContextProvider } from "../../model-context/types.js";
import type { ThreadListRuntimeCore } from "./thread-list-runtime-core.js";
export type AssistantRuntimeCore = {
    readonly threads: ThreadListRuntimeCore;
    registerModelContextProvider: (provider: ModelContextProvider) => Unsubscribe;
    getModelContextProvider: () => ModelContextProvider;
    readonly RenderComponent?: ((...args: any[]) => unknown) | undefined;
};