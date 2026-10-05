import type { ClientOutput } from "@assistant-ui/store";
import type { AppendMessage, ThreadMessage } from "../../types/message.js";
import type { AddToolResultOptions, RespondToToolApprovalOptions, ResumeToolCallOptions, Unstable_RecordToolInteractionOptions } from "../../runtime/interfaces/thread-runtime-core.js";
import type { ExternalThreadQueueAdapter } from "../../runtime/queue/external-thread-queue-adapter.js";
import type { ExternalThreadBranchAdapter } from "../../runtime/branch/external-thread-branch-adapter.js";
import type { AttachmentAdapter } from "../../adapters/attachment.js";
import type { FeedbackAdapter } from "../../adapters/feedback.js";
import type { SpeechSynthesisAdapter } from "../../adapters/speech.js";
import type { ReadonlyJSONValue } from "assistant-stream/utils";
export type ExternalThreadMessage = ThreadMessage & {
    id: string;
};
export type ExternalThreadProps = {
    messages: readonly ExternalThreadMessage[];
    isRunning?: boolean;
    isLoading?: boolean | undefined;
    state?: ReadonlyJSONValue | undefined;
    extras?: unknown;
    /**
     * Whether sending new messages is currently disabled. When `true`, the
     * thread composer's input remains usable but `send()` is a no-op and
     * `composer.canSend` is `false`. Edit composers (saving message edits)
     * intentionally ignore this flag.
     */
    isSendDisabled?: boolean;
    /**
     * Callback for new messages (non-queue runtimes).
     * @note Unused when `queue` is provided — new messages are routed through `queue.enqueue` instead.
     */
    onNew?: (message: AppendMessage) => void;
    onEdit?: (message: AppendMessage) => void;
    onReload?: (parentId: string | null) => void;
    onStartRun?: () => void;
    onCancel?: () => void;
    onResume?: (() => void) | undefined;
    /**
     * Handler for re-fetching this thread's state in place, driving
     * `threads.reloadMainThread()`. Unrelated to `onReload`, which re-generates
     * an assistant message. Presence enables the `refetchThread` capability;
     * rejections propagate to the caller.
     */
    onRefetchThread?: (() => Promise<void>) | undefined;
    onAddToolResult?: ((options: AddToolResultOptions) => void) | undefined;
    /** Callback for resuming a tool call that is waiting for human input. */
    onResumeToolCall?: ((options: ResumeToolCallOptions) => void) | undefined;
    onLoadExternalState?: ((state: unknown) => void) | undefined;
    attachmentAdapter?: AttachmentAdapter | undefined;
    feedbackAdapter?: FeedbackAdapter | undefined;
    speechAdapter?: SpeechSynthesisAdapter | undefined;
    /** Queue adapter for runtimes that support message queuing and steering. */
    queue?: ExternalThreadQueueAdapter;
    /** Branch adapter for runtimes that track sibling variants of messages. */
    branches?: ExternalThreadBranchAdapter;
    /** Callback for tool approval decisions. Absent: responding to an approval throws a capability error. */
    onRespondToToolApproval?: (options: RespondToToolApprovalOptions) => void | Promise<void>;
    unstable_onRecordToolInteraction?: ((options: Unstable_RecordToolInteractionOptions) => void | Promise<void>) | undefined;
};
export declare const ExternalThread: import("@assistant-ui/tap").Resource<ClientOutput<"thread">, [ExternalThreadProps]>;