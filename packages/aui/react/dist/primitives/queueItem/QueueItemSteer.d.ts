import { type ActionButtonElement, type ActionButtonProps } from "../../utils/createActionButton.js";
declare const useQueueItemSteer: () => () => void;
export declare namespace QueueItemPrimitiveSteer {
    type Element = ActionButtonElement;
    type Props = ActionButtonProps<typeof useQueueItemSteer>;
}
/**
 * A button that steers the current run to process this queue item immediately.
 *
 * @example
 * ```tsx
 * <QueueItemPrimitive.Steer>Run Now</QueueItemPrimitive.Steer>
 * ```
 */
export declare const QueueItemPrimitiveSteer: import("react").ForwardRefExoticComponent<Omit<Omit<import("react").ClassAttributes<HTMLButtonElement> & import("react").ButtonHTMLAttributes<HTMLButtonElement> & {
    asChild?: boolean;
}, "ref"> & {
    render?: import("react").ReactElement | undefined;
} & import("react").RefAttributes<HTMLButtonElement>, "ref"> & import("react").RefAttributes<HTMLButtonElement>>;
export {};