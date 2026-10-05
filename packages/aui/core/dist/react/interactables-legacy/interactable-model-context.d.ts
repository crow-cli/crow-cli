import type { Tool, toJSONSchema } from "assistant-stream";
import type { InteractableDefinition } from "./scopes.js";
export type StateJSONSchema = ReturnType<typeof toJSONSchema>;
export declare function buildInteractableModelContext(definitions: Record<string, InteractableDefinition>, schemaCache: Map<string, StateJSONSchema>, setDefState: (id: string, updater: (prev: unknown) => unknown) => void): {
    system: string;
    tools: Record<string, Tool<any, any>>;
} | undefined;