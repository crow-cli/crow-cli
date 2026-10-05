import { type ComponentPropsWithoutRef } from "react";
import type { PreComponent } from "./types.js";
export declare const PreContext: import("react").Context<Omit<Omit<import("react").DetailedHTMLProps<import("react").HTMLAttributes<HTMLPreElement>, HTMLPreElement>, "ref"> & {
    node?: import("hast").Element | undefined;
}, "children"> | null>;
export declare const useIsMarkdownCodeBlock: () => boolean;
type PreOverrideProps = ComponentPropsWithoutRef<PreComponent> & {
    fallbackPre: PreComponent;
};
export declare const PreOverride: import("react").MemoExoticComponent<({ children, fallbackPre: FallbackPre, ...rest }: PreOverrideProps) => import("react").JSX.Element>;
export {};