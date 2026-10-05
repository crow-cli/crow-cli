import { type ComponentRef, type ComponentPropsWithoutRef, type MouseEventHandler } from "react";
import { Primitive } from "./Primitive.js";
type ActionButtonCallback<TProps> = (props: TProps) => MouseEventHandler<HTMLButtonElement> | null;
type PrimitiveButtonProps = ComponentPropsWithoutRef<typeof Primitive.button>;
export type ActionButtonProps<THook> = PrimitiveButtonProps & (THook extends (props: infer TProps) => unknown ? TProps : never);
export type ActionButtonElement = ComponentRef<typeof Primitive.button>;
export declare const createActionButton: <TProps>(displayName: string, useActionButton: ActionButtonCallback<TProps>, forwardProps?: (keyof NonNullable<TProps>)[]) => import("react").ForwardRefExoticComponent<import("react").PropsWithoutRef<Omit<Omit<import("react").ClassAttributes<HTMLButtonElement> & import("react").ButtonHTMLAttributes<HTMLButtonElement> & {
    asChild?: boolean;
}, "ref"> & {
    render?: import("react").ReactElement | undefined;
} & import("react").RefAttributes<HTMLButtonElement>, "ref"> & TProps> & import("react").RefAttributes<HTMLButtonElement>>;
export {};