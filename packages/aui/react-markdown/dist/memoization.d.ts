import type { Element } from "hast";
import { type ComponentProps, type ComponentType, type ElementType } from "react";
import type { CodeHeaderProps, SyntaxHighlighterProps } from "./overrides/types.js";
type Components = {
    [Key in Extract<ElementType, string>]?: ComponentType<ComponentProps<Key>>;
} & {
    SyntaxHighlighter?: ComponentType<Omit<SyntaxHighlighterProps, "node">> | undefined;
    CodeHeader?: ComponentType<Omit<CodeHeaderProps, "node">> | undefined;
};
export declare const areNodesEqual: (prev: Element | undefined, next: Element | undefined) => boolean;
export declare const memoCompareNodes: (prev: {
    node?: Element | undefined;
}, next: {
    node?: Element | undefined;
}) => boolean;
export declare const memoizeMarkdownComponents: (components?: Components) => {
    [k: string]: import("react").MemoExoticComponent<({ node, ...props }: {
        node?: Element;
    }) => import("react").JSX.Element> | undefined;
};
export {};