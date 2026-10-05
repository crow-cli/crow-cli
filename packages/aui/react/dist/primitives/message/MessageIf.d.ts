import type { FC, PropsWithChildren } from "react";
import type { RequireAtLeastOne } from "../../utils/RequireAtLeastOne.js";
type MessageIfFilters = {
    user: boolean | undefined;
    assistant: boolean | undefined;
    system: boolean | undefined;
    hasBranches: boolean | undefined;
    copied: boolean | undefined;
    lastOrHover: boolean | undefined;
    last: boolean | undefined;
    speaking: boolean | undefined;
    hasAttachments: boolean | undefined;
    hasContent: boolean | undefined;
    submittedFeedback: "positive" | "negative" | null | undefined;
};
type UseMessageIfProps = RequireAtLeastOne<MessageIfFilters>;
export declare namespace MessagePrimitiveIf {
    type Props = PropsWithChildren<UseMessageIfProps>;
}
/**
 * @deprecated Use `<AuiIf condition={(s) => s.message...} />` instead.
 */
export declare const MessagePrimitiveIf: FC<MessagePrimitiveIf.Props>;
export {};