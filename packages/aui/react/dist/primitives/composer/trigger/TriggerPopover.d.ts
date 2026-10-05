import type { Unstable_TriggerAdapter } from "@assistant-ui/core";
import { type ComponentPropsWithoutRef, type ComponentRef } from "react";
import { Primitive } from "../../../utils/Primitive.js";
import { type TriggerPopoverResourceOutput } from "./TriggerPopoverResource.js";
import type { TriggerBehavior } from "./triggerSelectionResource.js";
import type { TriggerMatcher } from "./detectTrigger.js";
export declare const useTriggerPopoverScopeContext: () => TriggerPopoverResourceOutput;
export declare const useTriggerPopoverScopeContextOptional: () => TriggerPopoverResourceOutput | null;
/** Registration API exposed to behavior sub-primitives. */
export type TriggerBehaviorRegistration = {
    register(behavior: TriggerBehavior): () => void;
};
/** Obtain the registration handle from the parent `<TriggerPopover>`. */
export declare const useTriggerBehaviorRegistration: () => TriggerBehaviorRegistration;
export declare namespace ComposerPrimitiveTriggerPopover {
    type Element = ComponentRef<typeof Primitive.div>;
    type Props = Omit<ComponentPropsWithoutRef<typeof Primitive.div>, "onSelect"> & {
        /** The character(s) that activate this trigger (e.g. `"@"`, `"/"`). Also serves as the trigger identity within the root. */
        readonly char: string;
        /** Overrides trigger detection for both textarea and Lexical inputs. `endOffset` is the exclusive replace bound. */
        readonly matcher?: TriggerMatcher | undefined;
        /** Adapter providing categories and items. */
        readonly adapter?: Unstable_TriggerAdapter | undefined;
        /** Whether the adapter is resolving items, surfaced to the popover scope for async sources. @default false */
        readonly isLoading?: boolean | undefined;
    };
}
/**
 * Declares a trigger and renders its popover container. The popover only
 * renders its DOM (and children) when the trigger character is active in the
 * composer input and a behavior sub-primitive has been registered.
 *
 * A behavior is contributed by rendering exactly one of
 * `<TriggerPopover.Directive>` or `<TriggerPopover.Action>` as a child. Without
 * a behavior the trigger stays closed.
 *
 * Must be placed inside `ComposerPrimitive.Unstable_TriggerPopoverRoot`.
 *
 * @example
 * ```tsx
 * <ComposerPrimitive.Unstable_TriggerPopover
 *   char="@"
 *   adapter={mentionAdapter}
 * >
 *   <ComposerPrimitive.Unstable_TriggerPopover.Directive formatter={formatter} />
 *   <ComposerPrimitive.Unstable_TriggerPopoverCategories>
 *     {(cats) => cats.map(...)}
 *   </ComposerPrimitive.Unstable_TriggerPopoverCategories>
 *   <ComposerPrimitive.Unstable_TriggerPopoverItems>
 *     {(items) => items.map(...)}
 *   </ComposerPrimitive.Unstable_TriggerPopoverItems>
 * </ComposerPrimitive.Unstable_TriggerPopover>
 * ```
 */
export declare const ComposerPrimitiveTriggerPopover: import("react").ForwardRefExoticComponent<Omit<Omit<Omit<import("react").ClassAttributes<HTMLDivElement> & import("react").HTMLAttributes<HTMLDivElement> & {
    asChild?: boolean;
}, "ref"> & {
    render?: import("react").ReactElement | undefined;
} & import("react").RefAttributes<HTMLDivElement>, "ref">, "onSelect"> & {
    /** The character(s) that activate this trigger (e.g. `"@"`, `"/"`). Also serves as the trigger identity within the root. */
    readonly char: string;
    /** Overrides trigger detection for both textarea and Lexical inputs. `endOffset` is the exclusive replace bound. */
    readonly matcher?: TriggerMatcher | undefined;
    /** Adapter providing categories and items. */
    readonly adapter?: Unstable_TriggerAdapter | undefined;
    /** Whether the adapter is resolving items, surfaced to the popover scope for async sources. @default false */
    readonly isLoading?: boolean | undefined;
} & import("react").RefAttributes<HTMLDivElement>>;