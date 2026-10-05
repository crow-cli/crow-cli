import { type ComponentPropsWithoutRef, type ComponentType } from "react";
import type { CodeComponent, CodeHeaderProps, PreComponent, SyntaxHighlighterProps } from "./types.js";
import { type ComponentsByLanguage } from "../code-fence.js";
export type CodeOverrideProps = ComponentPropsWithoutRef<CodeComponent> & {
    components: {
        Pre: PreComponent;
        Code: CodeComponent;
        CodeHeader: ComponentType<CodeHeaderProps>;
        SyntaxHighlighter: ComponentType<SyntaxHighlighterProps>;
    };
    componentsByLanguage?: ComponentsByLanguage | undefined;
};
export declare const compareComponentsByLanguage: (prev: Record<string, ComponentsByLanguage[string] | undefined> | undefined, next: Record<string, ComponentsByLanguage[string] | undefined> | undefined) => boolean;
export declare const CodeOverride: import("react").NamedExoticComponent<CodeOverrideProps>;