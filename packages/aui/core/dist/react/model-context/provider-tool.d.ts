import type { Tool } from "assistant-stream";
type ProviderToolDefinition<TArgs extends Record<string, unknown>> = Extract<Tool<TArgs, unknown>, {
    type: "provider";
}>;
export type ProviderToolConfig<TArgs extends Record<string, unknown> = Record<string, unknown>> = Pick<ProviderToolDefinition<TArgs>, "providerId" | "args" | "parameters" | "providerOptions" | "supportsDeferredResults">;
/**
 * Marks a tool as provider-executed. The use-generative compiler converts
 * `execute: providerTool(...)` into a `type: "provider"` tool entry.
 */
export declare function providerTool(_config: ProviderToolConfig): never;
export {};