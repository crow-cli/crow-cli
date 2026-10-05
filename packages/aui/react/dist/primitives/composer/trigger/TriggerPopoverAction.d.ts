import type { Unstable_DirectiveFormatter, Unstable_TriggerItem } from "@assistant-ui/core";
import { type FC } from "react";
export declare namespace ComposerPrimitiveTriggerPopoverAction {
    type Props = {
        /** Defaults to `unstable_defaultDirectiveFormatter`. */
        readonly formatter?: Unstable_DirectiveFormatter | undefined;
        /** Fires the moment an item is selected; runs regardless of `removeOnExecute`. */
        readonly onExecute: (item: Unstable_TriggerItem) => void;
        /** When true, strips the trigger text after executing. Defaults to `false` (keeps audit-trail chip). */
        readonly removeOnExecute?: boolean | undefined;
    };
}
/**
 * Configures a `<TriggerPopover>` to fire a handler when an item is selected,
 * optionally leaving a directive chip behind as an audit trail. Render exactly
 * one behavior sub-primitive per `<TriggerPopover>`.
 *
 * Exposed as `ComposerPrimitive.Unstable_TriggerPopover.Action`.
 *
 * @example
 * ```tsx
 * <ComposerPrimitive.Unstable_TriggerPopover char="/" adapter={slashAdapter}>
 *   <ComposerPrimitive.Unstable_TriggerPopover.Action
 *     onExecute={(item) => commandHandlers[item.id]?.()}
 *     removeOnExecute={false}
 *   />
 * </ComposerPrimitive.Unstable_TriggerPopover>
 * ```
 */
export declare const ComposerPrimitiveTriggerPopoverAction: FC<ComposerPrimitiveTriggerPopoverAction.Props>;