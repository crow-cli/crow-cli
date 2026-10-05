import type { FC, PropsWithChildren } from "react";
type ComposerIfFilters = {
    /** Whether the composer is in editing mode */
    editing: boolean | undefined;
    /** Whether dictation is currently active */
    dictation: boolean | undefined;
};
export type RequireAtLeastOne<T, Keys extends keyof T = keyof T> = Pick<T, Exclude<keyof T, Keys>> & {
    [K in Keys]-?: Required<Pick<T, K>> & Partial<Pick<T, Exclude<Keys, K>>>;
}[Keys];
export type UseComposerIfProps = RequireAtLeastOne<ComposerIfFilters>;
export declare namespace ComposerPrimitiveIf {
    type Props = PropsWithChildren<UseComposerIfProps>;
}
/**
 * @deprecated Use `<AuiIf condition={(s) => s.composer...} />` instead.
 */
export declare const ComposerPrimitiveIf: FC<ComposerPrimitiveIf.Props>;
export {};