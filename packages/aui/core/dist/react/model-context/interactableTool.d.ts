import type { ReactNode } from "react";
import type { Unstable_InteractableStateSchema } from "../types/scopes/interactables.js";
import type { ToolDefinition } from "./toolbox.js";
import { type Unstable_InferInteractableState, type Unstable_InteractableVersionInfo } from "./useInteractable.js";
export type Unstable_InteractableToolRenderProps<TState> = {
    /**
     * The live state. While `streaming` is true, fields the model has not
     * finished generating may still be missing.
     */
    state: TState;
    setState: (updater: TState | ((prev: TState) => TState)) => void;
    /**
     * This message's version of the instance: its state as of this point in the
     * conversation, whether it is the most recent edit, and a `restore()` back
     * to it. `undefined` while streaming.
     */
    version: Unstable_InteractableVersionInfo<TState> | undefined;
    id: string;
    /** True while the tool call's arguments are still streaming in. */
    streaming: boolean;
};
export type Unstable_InteractableToolConfig<TSchema extends Unstable_InteractableStateSchema> = {
    description: string;
    stateSchema: TSchema;
    render: (props: Unstable_InteractableToolRenderProps<Unstable_InferInteractableState<TSchema>>) => ReactNode;
};
/**
 * Defines a tool that creates a thread-scoped interactable from its arguments,
 * for assignment to a toolkit entry — the entry key is the interactable name:
 *
 * ```tsx
 * notepad: unstable_interactableTool({
 *   description: "A notepad the user can read and edit.",
 *   stateSchema: notepadSchema,
 *   render: (props) => <Notepad {...props} />,
 * }),
 * ```
 *
 * `render` shows at the creating call and — installed automatically — at every
 * `update_{name}` call, with streaming previews, instance-id wiring, and
 * registration handled. It receives the live `state`/`setState` plus this
 * message's `version`; whether older messages render frozen history or stay
 * live-editable is the render function's choice.
 *
 * @deprecated Unstable / Experimental (not actually removed).
 */
export declare const unstable_interactableTool: <TSchema extends Unstable_InteractableStateSchema>(config: Unstable_InteractableToolConfig<TSchema>) => ToolDefinition<Record<string, unknown>, {
    success: true;
}>;