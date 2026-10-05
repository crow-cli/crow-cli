import type { Tool } from "assistant-stream";
import { toJSONSchema } from "assistant-stream";
import type { Unstable_InteractableDefinition } from "../types/scopes/interactables.js";
export type StateJSONSchema = ReturnType<typeof toJSONSchema>;
export declare function buildInteractableModelContext(definitions: Record<string, Unstable_InteractableDefinition>, schemaCache: Map<string, StateJSONSchema>, setDefState: (id: string, updater: (prev: unknown) => unknown) => void, getCurrentDefinitions: () => Record<string, Unstable_InteractableDefinition>, streamBaselines?: Map<string, {
    targetId: string;
    state: unknown;
}>): {
    tools: Record<string, Tool<any, any>>;
    unstable_composerMetadata?: Record<string, unknown>;
} | undefined;