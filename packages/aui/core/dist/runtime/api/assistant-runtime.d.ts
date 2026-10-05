import type { Unsubscribe } from "../../types/unsubscribe.js";
import type { ModelContextProvider } from "../../model-context/types.js";
import type { AssistantRuntimeCore } from "../interfaces/assistant-runtime-core.js";
import type { ThreadRuntime } from "./thread-runtime.js";
import { type ThreadListRuntime, ThreadListRuntimeImpl } from "./thread-list-runtime.js";
export type AssistantRuntime = {
    /**
     * The threads in this assistant.
     */
    readonly threads: ThreadListRuntime;
    /**
     * The currently selected main thread. Equivalent to `threads.main`.
     */
    readonly thread: ThreadRuntime;
    /**
     * Register a model context provider. Model context providers are configuration such as system message, temperature, etc. that are set in the frontend.
     *
     * @param provider The model context provider to register.
     */
    registerModelContextProvider(provider: ModelContextProvider): Unsubscribe;
};
export declare class AssistantRuntimeImpl implements AssistantRuntime {
    readonly threads: ThreadListRuntimeImpl;
    readonly _thread: ThreadRuntime;
    private readonly _core;
    constructor(_core: AssistantRuntimeCore);
    protected __internal_bindMethods(): void;
    get thread(): ThreadRuntime;
    registerModelContextProvider(provider: ModelContextProvider): Unsubscribe;
}