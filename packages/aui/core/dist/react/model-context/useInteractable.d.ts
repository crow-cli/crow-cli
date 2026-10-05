import type { Unstable_InteractableStateSchema } from "../types/scopes/interactables.js";
import type { ToolCallMessagePartComponent } from "../types/MessagePartComponentTypes.js";
/**
 * The state type described by an interactable's `stateSchema`. Resolves the
 * output type of a StandardSchemaV1 schema (e.g. Zod); plain JSON Schema
 * falls back to `unknown`.
 */
export type Unstable_InferInteractableState<TSchema> = TSchema extends {
    "~standard": {
        types?: {
            output: infer TOutput;
        } | undefined;
    };
} ? TOutput : unknown;
/**
 * One message's version of an interactable, for components rendered inside
 * tool-call parts. Show `state` to display history; call `restore()` to set
 * the live instance back to it.
 */
export type Unstable_InteractableVersionInfo<TState> = {
    /** The interactable's state as it was at this message. */
    state: TState;
    /** Whether this message holds the instance's most recent tool-driven version. */
    isLatest: boolean;
    /** Sets the live state back to this version. */
    restore: () => void;
};
/**
 * Unstable / Experimental — the interactables API is still evolving and may change in any release.
 * @deprecated Unstable / Experimental (not actually removed).
 */
export type Unstable_InteractableConfig<TSchema extends Unstable_InteractableStateSchema> = {
    description: string;
    stateSchema: TSchema;
    initialState: Unstable_InferInteractableState<TSchema>;
    /** Unique instance ID; required to address this instance when multiple interactables share a name. Auto-generated if omitted. */
    id?: string | undefined;
    /**
     * Component installed as the tool UI for this interactable's `update_{name}`
     * tool calls, so a model edit re-renders the interactable at the message
     * that made it instead of only mutating an earlier one. Prefer
     * `unstable_interactableTool`, which wires this up. Pass a stable component reference;
     * changing identity re-registers the tool UI.
     */
    updateRender?: ToolCallMessagePartComponent | undefined;
};
/**
 * Registers an interactable with the AI assistant and returns its live state,
 * like `useState` that the model can also read and update.
 *
 * Call this once per place that shows the interactable. Other components can
 * read and write the same instance by passing its `id` to
 * `unstable_useInteractableState`.
 *
 * For tool-created interactables rendered inside tool-call message parts,
 * `version` carries this message's version of the instance — its state as of
 * that point in the conversation, whether it is the most recent tool-driven
 * version, and a `restore()` back to it. Whether older messages render frozen history or stay
 * live-editable is the component's choice. Inside an `update_{name}` part the
 * instance `id` is inferred from the call, so the same component works at the
 * creating call and at update calls.
 *
 * @deprecated Unstable / Experimental (not actually removed).
 */
export declare const unstable_useInteractable: <TSchema extends Unstable_InteractableStateSchema>(name: string, config: Unstable_InteractableConfig<TSchema>) => readonly [
    Unstable_InferInteractableState<TSchema>,
    {
        id: string;
        version: Unstable_InteractableVersionInfo<Unstable_InferInteractableState<TSchema>> | undefined;
        setState: (updater: Unstable_InferInteractableState<TSchema> | ((prev: Unstable_InferInteractableState<TSchema>) => Unstable_InferInteractableState<TSchema>)) => void;
        isPending: boolean;
        error: unknown;
        flush: () => Promise<void>;
    }
];