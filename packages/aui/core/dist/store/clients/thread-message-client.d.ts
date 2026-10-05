import type { ThreadMessage } from "../../types/message.js";
import type { ComposerSubmission } from "../../runtime/interfaces/composer-runtime-core.js";
import type { ClientOutput } from "@assistant-ui/store";
export type ThreadMessageClientProps = {
    message: ThreadMessage;
    index: number;
    isLast?: boolean;
    branchNumber?: number;
    branchCount?: number;
    /** Set when this row is a composer submission rather than a thread message. */
    submission?: ComposerSubmission | undefined;
};
export declare const ThreadMessageClient: import("@assistant-ui/tap").Resource<ClientOutput<"message">, [ThreadMessageClientProps]>;