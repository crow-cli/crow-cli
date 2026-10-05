import { type ReactNode } from "react";
import type { QueueItemState } from "../../../store/scopes/queue-item.js";
export declare namespace ComposerPrimitiveQueue {
    type Props = {
        /** Render function called for each queue item. Receives the queue item state. */
        children: (value: {
            queueItem: QueueItemState;
        }) => ReactNode;
    };
}
/**
 * Renders all queue items in the composer.
 *
 * @example
 * ```tsx
 * <ComposerPrimitive.Queue>
 *   {({ queueItem }) => (
 *     <div>
 *       <QueueItemPrimitive.Text />
 *       <QueueItemPrimitive.Steer>Run Now</QueueItemPrimitive.Steer>
 *     </div>
 *   )}
 * </ComposerPrimitive.Queue>
 * ```
 */
export declare const ComposerPrimitiveQueue: import("react").NamedExoticComponent<{
    children: (value: {
        queueItem: QueueItemState;
    }) => ReactNode;
}>;