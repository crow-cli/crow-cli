import type { ComponentType, ReactNode } from "react";
import type { PreComponent, CodeComponent, CodeHeaderProps } from "./types.js";
import type { Element } from "hast";
export declare const DefaultPre: PreComponent;
export declare const DefaultCode: CodeComponent;
export declare const DefaultCodeBlockContent: ComponentType<{
    node: Element | undefined;
    components: {
        Pre: PreComponent;
        Code: CodeComponent;
    };
    code: string | ReactNode | undefined;
}>;
export declare const DefaultCodeHeader: ComponentType<CodeHeaderProps>;