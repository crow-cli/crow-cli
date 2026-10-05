import { type ModelContext, type ModelContextProvider, type AssistantToolProps, type AssistantInstructionsConfig } from "./types.js";
import type { Unsubscribe } from "../types/unsubscribe.js";
import type { ModelContextRegistryToolHandle, ModelContextRegistryInstructionHandle, ModelContextRegistryProviderHandle } from "./registry-handles.js";
export declare class ModelContextRegistry implements ModelContextProvider {
    private _tools;
    private _instructions;
    private _contextProviders;
    private _subscribers;
    constructor();
    getModelContext(): ModelContext;
    subscribe(callback: () => void): Unsubscribe;
    private notifySubscribers;
    addTool<TArgs extends Record<string, unknown>, TResult>(tool: AssistantToolProps<TArgs, TResult>): ModelContextRegistryToolHandle<TArgs, TResult>;
    addInstruction(config: string | AssistantInstructionsConfig): ModelContextRegistryInstructionHandle;
    addProvider(provider: ModelContextProvider): ModelContextRegistryProviderHandle;
}