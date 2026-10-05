import type { ToolsClientSchema } from "./scopes/tools.js";
import type { DataRenderersClientSchema } from "./scopes/dataRenderers.js";
import type { InteractablesClientSchema as LegacyInteractablesClientSchema } from "../interactables-legacy/scopes.js";
import type { Unstable_InteractablesClientSchema } from "./scopes/interactables.js";
declare module "@assistant-ui/store" {
    interface ScopeRegistry {
        tools: ToolsClientSchema;
        dataRenderers: DataRenderersClientSchema;
        interactables: LegacyInteractablesClientSchema;
        unstable_interactables: Unstable_InteractablesClientSchema;
    }
}