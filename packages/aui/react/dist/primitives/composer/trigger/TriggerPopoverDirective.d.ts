import type { Unstable_DirectiveFormatter, Unstable_TriggerItem } from "@assistant-ui/core";
import { type FC } from "react";
export declare namespace ComposerPrimitiveTriggerPopoverDirective {
    type Props = {
        /** Defaults to `unstable_defaultDirectiveFormatter`. */
        readonly formatter?: Unstable_DirectiveFormatter | undefined;
        /** Fires after an item has been inserted into the composer. */
        readonly onInserted?: ((item: Unstable_TriggerItem) => void) | undefined;
    };
}
/**
 * Configures a `<TriggerPopover>` to insert a directive chip when an item is
 * selected. Render exactly one behavior sub-primitive per `<TriggerPopover>`.
 *
 * Exposed as `ComposerPrimitive.Unstable_TriggerPopover.Directive`.
 *
 * @example
 * ```tsx
 * <ComposerPrimitive.Unstable_TriggerPopover char="@" adapter={mentionAdapter}>
 *   <ComposerPrimitive.Unstable_TriggerPopover.Directive
 *     formatter={unstable_defaultDirectiveFormatter}
 *     onInserted={(item) => track("mention", item.id)}
 *   />
 * </ComposerPrimitive.Unstable_TriggerPopover>
 * ```
 */
export declare const ComposerPrimitiveTriggerPopoverDirective: FC<ComposerPrimitiveTriggerPopoverDirective.Props>;