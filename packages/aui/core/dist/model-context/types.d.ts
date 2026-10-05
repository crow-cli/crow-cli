import type { Unsubscribe } from "../types/unsubscribe.js";
import type { Tool } from "assistant-stream";
export type LanguageModelV1CallSettings = {
    maxTokens?: number;
    temperature?: number;
    topP?: number;
    presencePenalty?: number;
    frequencyPenalty?: number;
    seed?: number;
    headers?: Record<string, string | undefined>;
};
export type LanguageModelConfig = {
    apiKey?: string;
    baseUrl?: string;
    modelName?: string;
    reasoningEffort?: string;
};
export type ModelContext = {
    priority?: number | undefined;
    system?: string | undefined;
    tools?: Record<string, Tool<any, any>> | undefined;
    callSettings?: LanguageModelV1CallSettings | undefined;
    config?: LanguageModelConfig | undefined;
    /**
     * Persisted message metadata pulled at send time and merged into the outgoing
     * user message's `metadata.custom` (not forwarded to the model directly).
     * Ignored by the transport, which only reads system/tools/callSettings/config.
     */
    unstable_composerMetadata?: Record<string, unknown> | undefined;
};
export type ModelContextProvider = {
    getModelContext: () => ModelContext;
    subscribe?: (callback: () => void) => Unsubscribe;
};
export type AssistantToolProps<TArgs extends Record<string, unknown>, TResult> = Tool<TArgs, TResult> & {
    toolName: string;
    render?: unknown;
};
export type AssistantInstructionsConfig = {
    disabled?: boolean | undefined;
    instruction: string;
};
export type AssistantContextConfig = {
    getContext: () => string;
    disabled?: boolean | undefined;
};
export declare const mergeModelContexts: (configSet: Set<ModelContextProvider>) => ModelContext;