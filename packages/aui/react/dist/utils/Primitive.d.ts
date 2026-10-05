import { type ComponentProps, type ComponentPropsWithoutRef, type ComponentRef, type ElementType, type ForwardRefExoticComponent, type ReactElement, type ReactNode, type RefAttributes } from "react";
import { Primitive as RadixPrimitive } from "radix-ui/internal";
import { Slot } from "radix-ui";
/**
 * Thin wrapper around Radix `Primitive` that adds `render` prop support.
 *
 * When `render` is provided, it is converted to the equivalent `asChild` pattern:
 *   render={<Comp props />} + children  →  asChild + <Comp props>{children}</Comp>
 *
 * All prop merging, ref composition, and event handler chaining remain handled
 * by Radix's battle-tested Slot implementation — we add zero custom logic for that.
 */
declare const NODES: readonly ["a", "button", "div", "form", "h2", "h3", "img", "input", "label", "li", "nav", "ol", "p", "select", "span", "svg", "ul"];
type PrimitiveNode = (typeof NODES)[number];
type WithRenderPropProps<T extends ElementType> = ComponentPropsWithoutRef<T> & {
    render?: ReactElement | undefined;
};
type PrimitiveProps<E extends PrimitiveNode> = WithRenderPropProps<(typeof RadixPrimitive)[E]>;
/**
 * Composes a `render` element at a call site that has already computed its props.
 *
 * `withRenderProp` wraps a component; this covers the case where the props are
 * already in hand and the composition happens inline.
 */
declare function renderSlot(render: ReactElement, children: ReactNode, props: ComponentProps<typeof Slot.Root>): ReactElement;
declare function withRenderProp<T extends ElementType>(Component: T): ForwardRefExoticComponent<WithRenderPropProps<T> & RefAttributes<ComponentRef<T>>>;
declare const Primitive: {
    input: ForwardRefExoticComponent<Omit<import("react").ClassAttributes<HTMLInputElement> & import("react").InputHTMLAttributes<HTMLInputElement> & {
        asChild?: boolean;
    }, "ref"> & {
        render?: ReactElement | undefined;
    } & RefAttributes<HTMLInputElement>>;
    select: ForwardRefExoticComponent<Omit<import("react").ClassAttributes<HTMLSelectElement> & import("react").SelectHTMLAttributes<HTMLSelectElement> & {
        asChild?: boolean;
    }, "ref"> & {
        render?: ReactElement | undefined;
    } & RefAttributes<HTMLSelectElement>>;
    div: ForwardRefExoticComponent<Omit<import("react").ClassAttributes<HTMLDivElement> & import("react").HTMLAttributes<HTMLDivElement> & {
        asChild?: boolean;
    }, "ref"> & {
        render?: ReactElement | undefined;
    } & RefAttributes<HTMLDivElement>>;
    a: ForwardRefExoticComponent<Omit<import("react").ClassAttributes<HTMLAnchorElement> & import("react").AnchorHTMLAttributes<HTMLAnchorElement> & {
        asChild?: boolean;
    }, "ref"> & {
        render?: ReactElement | undefined;
    } & RefAttributes<HTMLAnchorElement>>;
    button: ForwardRefExoticComponent<Omit<import("react").ClassAttributes<HTMLButtonElement> & import("react").ButtonHTMLAttributes<HTMLButtonElement> & {
        asChild?: boolean;
    }, "ref"> & {
        render?: ReactElement | undefined;
    } & RefAttributes<HTMLButtonElement>>;
    form: ForwardRefExoticComponent<Omit<import("react").ClassAttributes<HTMLFormElement> & import("react").FormHTMLAttributes<HTMLFormElement> & {
        asChild?: boolean;
    }, "ref"> & {
        render?: ReactElement | undefined;
    } & RefAttributes<HTMLFormElement>>;
    h2: ForwardRefExoticComponent<Omit<import("react").ClassAttributes<HTMLHeadingElement> & import("react").HTMLAttributes<HTMLHeadingElement> & {
        asChild?: boolean;
    }, "ref"> & {
        render?: ReactElement | undefined;
    } & RefAttributes<HTMLHeadingElement>>;
    h3: ForwardRefExoticComponent<Omit<import("react").ClassAttributes<HTMLHeadingElement> & import("react").HTMLAttributes<HTMLHeadingElement> & {
        asChild?: boolean;
    }, "ref"> & {
        render?: ReactElement | undefined;
    } & RefAttributes<HTMLHeadingElement>>;
    img: ForwardRefExoticComponent<Omit<import("react").ClassAttributes<HTMLImageElement> & import("react").ImgHTMLAttributes<HTMLImageElement> & {
        asChild?: boolean;
    }, "ref"> & {
        render?: ReactElement | undefined;
    } & RefAttributes<HTMLImageElement>>;
    label: ForwardRefExoticComponent<Omit<import("react").ClassAttributes<HTMLLabelElement> & import("react").LabelHTMLAttributes<HTMLLabelElement> & {
        asChild?: boolean;
    }, "ref"> & {
        render?: ReactElement | undefined;
    } & RefAttributes<HTMLLabelElement>>;
    li: ForwardRefExoticComponent<Omit<import("react").ClassAttributes<HTMLLIElement> & import("react").LiHTMLAttributes<HTMLLIElement> & {
        asChild?: boolean;
    }, "ref"> & {
        render?: ReactElement | undefined;
    } & RefAttributes<HTMLLIElement>>;
    nav: ForwardRefExoticComponent<Omit<import("react").ClassAttributes<HTMLElement> & import("react").HTMLAttributes<HTMLElement> & {
        asChild?: boolean;
    }, "ref"> & {
        render?: ReactElement | undefined;
    } & RefAttributes<HTMLElement>>;
    ol: ForwardRefExoticComponent<Omit<import("react").ClassAttributes<HTMLOListElement> & import("react").OlHTMLAttributes<HTMLOListElement> & {
        asChild?: boolean;
    }, "ref"> & {
        render?: ReactElement | undefined;
    } & RefAttributes<HTMLOListElement>>;
    p: ForwardRefExoticComponent<Omit<import("react").ClassAttributes<HTMLParagraphElement> & import("react").HTMLAttributes<HTMLParagraphElement> & {
        asChild?: boolean;
    }, "ref"> & {
        render?: ReactElement | undefined;
    } & RefAttributes<HTMLParagraphElement>>;
    span: ForwardRefExoticComponent<Omit<import("react").ClassAttributes<HTMLSpanElement> & import("react").HTMLAttributes<HTMLSpanElement> & {
        asChild?: boolean;
    }, "ref"> & {
        render?: ReactElement | undefined;
    } & RefAttributes<HTMLSpanElement>>;
    ul: ForwardRefExoticComponent<Omit<import("react").ClassAttributes<HTMLUListElement> & import("react").HTMLAttributes<HTMLUListElement> & {
        asChild?: boolean;
    }, "ref"> & {
        render?: ReactElement | undefined;
    } & RefAttributes<HTMLUListElement>>;
    svg: ForwardRefExoticComponent<Omit<import("react").SVGProps<SVGSVGElement> & {
        asChild?: boolean;
    }, "ref"> & {
        render?: ReactElement | undefined;
    } & RefAttributes<SVGSVGElement>>;
};
export { Primitive, renderSlot, withRenderProp };
export type { PrimitiveProps, WithRenderPropProps };