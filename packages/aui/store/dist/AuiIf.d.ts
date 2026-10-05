import type { FC, PropsWithChildren } from "react";
import type { AssistantState } from "./types/client.js";
export declare namespace AuiIf {
    /** Props for `AuiIf`. */
    type Props = PropsWithChildren<{
        /** Selector deciding whether `children` render. */
        condition: AuiIf.Condition;
    }>;
    /** Boolean selector over the assistant state. */
    type Condition = (state: AssistantState) => boolean;
}
/** Renders `children` while `condition` selects `true` from the assistant state. */
export declare const AuiIf: FC<AuiIf.Props>;