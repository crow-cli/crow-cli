import type { Unstable_DirectiveFormatter, Unstable_TriggerItem } from "@assistant-ui/core";
import type { AssistantClient } from "@assistant-ui/store";
import type { DetectedTrigger } from "./triggerDetectionResource.js";
/** External override for selection (used by Lexical's DirectivePlugin). */
export type SelectItemOverride = (item: Unstable_TriggerItem) => boolean;
export type TriggerBehavior = {
    readonly kind: "directive";
    readonly formatter: Unstable_DirectiveFormatter;
    readonly onInserted?: (item: Unstable_TriggerItem) => void;
} | {
    readonly kind: "action";
    readonly formatter: Unstable_DirectiveFormatter;
    readonly onExecute: (item: Unstable_TriggerItem) => void;
    readonly removeOnExecute?: boolean;
};
export type TriggerSelectionResourceOutput = {
    /** Select an item — runs override (if any) then applies behavior. */
    selectItem(item: Unstable_TriggerItem): void;
    /** Close the popover (moves cursor before trigger to deactivate detection). */
    close(): void;
    /** Register a Lexical-style selection override. Returns unregister fn. */
    registerSelectItemOverride(fn: SelectItemOverride): () => void;
};
export declare const TriggerSelectionResource: import("@assistant-ui/tap").Resource<TriggerSelectionResourceOutput, [{
    behavior: TriggerBehavior | undefined;
    trigger: DetectedTrigger | null;
    aui: AssistantClient;
    triggerChar: string;
    setCursorPosition: (pos: number) => void;
    /** Called after a successful selection so the parent can reset nav state. */
    onSelected: () => void;
}]>;