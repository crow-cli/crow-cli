import type { Toolkit, ToolkitDefinition, ToolkitDefinitionEntryWithParameters } from "./toolbox.js";
/**
 * Toolkit authoring helper. Accepts the permissive {@link ToolkitDefinition}
 * (a generative `backend` tool may carry its server `execute`) and types the
 * result as the canonical {@link Toolkit}.
 *
 * In a `"use generative"` file, the compiler strips the wrapper per build so it
 * can split schemas, renderers, and executors across the client/server boundary.
 * Outside generative compilation, it returns the toolkit unchanged and can be
 * used for plain frontend/backend/human toolkit objects.
 */
export declare function defineToolkit<TArgsByName extends {
    [K in keyof TArgsByName]: Record<string, unknown>;
}, TResultByName extends {
    [K in keyof TArgsByName]: unknown;
} = {
    [K in keyof TArgsByName]: any;
}>(_definition: {
    [K in keyof TArgsByName]: ToolkitDefinitionEntryWithParameters<TArgsByName[K], TResultByName[K]>;
}): Toolkit & {
    [K in keyof TArgsByName]: ToolkitDefinitionEntryWithParameters<TArgsByName[K], TResultByName[K]>;
};
export declare function defineToolkit<const TDefinition extends ToolkitDefinition>(_definition: TDefinition): Toolkit & TDefinition;