import { type SmoothOptions } from "@assistant-ui/react";
import { type ElementType, type ForwardRefExoticComponent, type RefAttributes, type ComponentPropsWithoutRef, type ComponentType } from "react";
import { type Options } from "react-markdown";
import type { SyntaxHighlighterProps, CodeHeaderProps } from "../overrides/types.js";
import type { ComponentsByLanguage } from "../code-fence.js";
import type { Primitive } from "@radix-ui/react-primitive";
type PrimitiveDivProps = ComponentPropsWithoutRef<typeof Primitive.div>;
export type MarkdownTextPrimitiveProps = Omit<Options, "components" | "children"> & {
    className?: string | undefined;
    containerProps?: Omit<PrimitiveDivProps, "children" | "asChild"> | undefined;
    containerComponent?: ElementType | undefined;
    components?: (NonNullable<Options["components"]> & {
        SyntaxHighlighter?: ComponentType<SyntaxHighlighterProps> | undefined;
        CodeHeader?: ComponentType<CodeHeaderProps> | undefined;
    }) | undefined;
    /**
     * Language-specific component overrides.
     * @example { mermaid: { SyntaxHighlighter: MermaidDiagram } }
     */
    componentsByLanguage?: ComponentsByLanguage | undefined;
    /**
     * Whether to enable smooth text streaming animation.
     * When enabled, text appears with a typing effect as it streams in.
     * Pass a `SmoothOptions` object to tune the reveal rate.
     * Auto-disables under `prefers-reduced-motion: reduce`.
     * @default true
     */
    smooth?: boolean | SmoothOptions | undefined;
    /**
     * Defers markdown parsing and rendering to a lower priority via React's
     * `useDeferredValue`, so urgent work (typing, scrolling) is not blocked by
     * re-parsing the growing message on every streamed token. Intermediate
     * streaming states may be skipped under load; the final text always renders.
     *
     * Must stay constant for the lifetime of the component: the deferred path is
     * a separate component, so toggling this remounts the rendered markdown.
     *
     * @default false
     */
    defer?: boolean | undefined;
    /**
     * Function to transform text before markdown processing.
     */
    preprocess?: (text: string) => string;
};
export declare const MarkdownTextPrimitive: ForwardRefExoticComponent<MarkdownTextPrimitiveProps> & RefAttributes<HTMLDivElement>;
export {};