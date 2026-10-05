import { type ActionButtonElement, type ActionButtonProps } from "../../utils/createActionButton.js";
declare const useQueueItemRemove: () => () => void;
export declare namespace QueueItemPrimitiveRemove {
    type Element = ActionButtonElement;
    type Props = ActionButtonProps<typeof useQueueItemRemove>;
}
/**
 * A button that removes this item from the queue.
 *
 * @example
 * ```tsx
 * <QueueItemPrimitive.Remove>×</QueueItemPrimitive.Remove>
 * ```
 */
export declare const QueueItemPrimitiveRemove: import("react").ForwardRefExoticComponent<Omit<Omit<import("react").ClassAttributes<HTMLButtonElement> & import("react").ButtonHTMLAttributes<HTMLButtonElement> & {
    asChild?: boolean;
}, "ref"> & {
    render?: import("react").ReactElement | undefined;
} & import("react").RefAttributes<HTMLButtonElement>, "ref"> & import("react").RefAttributes<HTMLButtonElement>>;
export {};