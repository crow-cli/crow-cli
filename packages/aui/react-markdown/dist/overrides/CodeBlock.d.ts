import { type ComponentType, type FC } from "react";
import type { CodeComponent, CodeHeaderProps, PreComponent, SyntaxHighlighterProps } from "./types.js";
import type { Element } from "hast";
export type CodeBlockProps = {
    node: Element | undefined;
    language: string;
    code: string;
    components: {
        Pre: PreComponent;
        Code: CodeComponent;
        CodeHeader: ComponentType<CodeHeaderProps>;
        SyntaxHighlighter: ComponentType<SyntaxHighlighterProps>;
    };
};
export declare const DefaultCodeBlock: FC<CodeBlockProps>;