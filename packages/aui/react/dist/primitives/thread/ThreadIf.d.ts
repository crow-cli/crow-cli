import type { FC, PropsWithChildren } from "react";
import type { RequireAtLeastOne } from "../../utils/RequireAtLeastOne.js";
type ThreadIfFilters = {
    empty: boolean | undefined;
    running: boolean | undefined;
    disabled: boolean | undefined;
};
type UseThreadIfProps = RequireAtLeastOne<ThreadIfFilters>;
export declare namespace ThreadPrimitiveIf {
    type Props = PropsWithChildren<UseThreadIfProps>;
}
/**
 * @deprecated Use `<AuiIf condition={(s) => s.thread...} />` instead.
 */
export declare const ThreadPrimitiveIf: FC<ThreadPrimitiveIf.Props>;
export {};