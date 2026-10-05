import type { ComposerSubmission } from "../../runtime/interfaces/composer-runtime-core.js";
import type { ThreadMessage } from "../../types/message.js";
/**
 * The thread row for a submission. Its attachments stay on the submission,
 * because a message only carries attachments it was delivered with.
 */
export declare const submissionThreadMessage: (submission: ComposerSubmission) => ThreadMessage;