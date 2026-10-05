export { ComposerPrimitiveTriggerPopoverRoot, useTriggerPopoverRootContext, useTriggerPopoverRootContextOptional, useTriggerPopoverTriggers, useTriggerPopoverTriggersOptional, type RegisteredTrigger, type TriggerPopoverRootContextValue, } from "./TriggerPopoverRootContext.js";
export { useTriggerPopoverScopeContext, useTriggerPopoverScopeContextOptional, } from "./TriggerPopover.js";
export { ComposerPrimitiveTriggerPopoverCategories, ComposerPrimitiveTriggerPopoverCategoryItem, } from "./TriggerPopoverCategories.js";
export { ComposerPrimitiveTriggerPopoverItems, ComposerPrimitiveTriggerPopoverItem, } from "./TriggerPopoverItems.js";
export { ComposerPrimitiveTriggerPopoverBack } from "./TriggerPopoverBack.js";
export type { TriggerBehavior } from "./triggerSelectionResource.js";
export type { TriggerMatch, TriggerMatcher } from "./detectTrigger.js";
import { ComposerPrimitiveTriggerPopoverAction } from "./TriggerPopoverAction.js";
import { ComposerPrimitiveTriggerPopoverDirective } from "./TriggerPopoverDirective.js";
export declare const ComposerPrimitiveTriggerPopover: import("react").ForwardRefExoticComponent<Omit<Omit<Omit<import("react").ClassAttributes<HTMLDivElement> & import("react").HTMLAttributes<HTMLDivElement> & {
    asChild?: boolean;
}, "ref"> & {
    render?: import("react").ReactElement | undefined;
} & import("react").RefAttributes<HTMLDivElement>, "ref">, "onSelect"> & {
    readonly char: string;
    readonly matcher?: import("./detectTrigger.js").TriggerMatcher | undefined;
    readonly adapter?: import("@assistant-ui/core").Unstable_TriggerAdapter | undefined;
    readonly isLoading?: boolean | undefined;
} & import("react").RefAttributes<HTMLDivElement>> & {
    Directive: import("react").FC<ComposerPrimitiveTriggerPopoverDirective.Props>;
    Action: import("react").FC<ComposerPrimitiveTriggerPopoverAction.Props>;
};