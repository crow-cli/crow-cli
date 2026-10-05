import type { Unsubscribe } from "../../types/unsubscribe.js";
import type { ModelContextProvider } from "../../model-context/types.js";
import { CompositeContextProvider } from "../../utils/composite-context-provider.js";
import type { AssistantRuntimeCore } from "../interfaces/assistant-runtime-core.js";
import type { ThreadListRuntimeCore } from "../interfaces/thread-list-runtime-core.js";
export declare abstract class BaseAssistantRuntimeCore implements AssistantRuntimeCore {
    protected readonly _contextProvider: CompositeContextProvider;
    abstract get threads(): ThreadListRuntimeCore;
    registerModelContextProvider(provider: ModelContextProvider): Unsubscribe;
    getModelContextProvider(): ModelContextProvider;
}