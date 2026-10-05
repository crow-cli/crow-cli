import { type Tool, type ToolModelContentPart } from "assistant-stream";
import { type ReadonlyJSONValue } from "assistant-stream/utils";
import type { ThreadMessage, ToolCallMessagePart } from "../../types/message.js";
/**
 * Streaming execution state for a frontend tool.
 */
export type ToolExecutionStatus = {
    type: "executing";
} | {
    type: "interrupt";
    payload: {
        type: "human";
        payload: unknown;
    };
};
export type AddToolResultCommand = {
    readonly type: "add-tool-result";
    readonly toolCallId: string;
    readonly toolName: string;
    readonly result: ReadonlyJSONValue;
    readonly isError: boolean;
    readonly artifact?: ReadonlyJSONValue;
    readonly modelContent?: readonly ToolModelContentPart[];
};
/**
 * Plain-class port of the former `useToolInvocations` React hook. Owns the
 * assistant-stream pipeline that drives client-side `streamCall` / `execute`
 * for tool-call parts surfaced by a thread runtime, plus the per-tool-call
 * status map that consumers render against.
 *
 * **Contract**: `streamCall` (and `execute`) fires exactly once per logical
 * `toolCallId`. Args mutations after first completion, result replacement,
 * and result clearing are *not* surfaced through additional `streamCall`
 * invocations — by design — so hosts cannot observe spurious re-fires of
 * side effects. The follow-up `reader.events()` API will expose those
 * post-completion transitions to consumers that opt in.
 *
 * State-transition safety: every public method that observes runtime state
 * (`setState`, `reset`, `abort`, `resume`) wraps its work in try/catch and
 * logs to `console.error` rather than throwing. The tracker is built into
 * the hot message-processing path, so a malformed snapshot must never crash
 * the host runtime. See ./EDGE_CASES.md for the known non-trivial state
 * transitions and what each does today.
 *
 * @deprecated Internal — for framework bindings; not a public API. May change without notice.
 */
export declare class ToolInvocationTracker {
    private readonly _getTools;
    private readonly _callbacks;
    private readonly _isClientToolCall;
    private readonly _entries;
    private readonly _humanInput;
    private readonly _executing;
    /**
     * Tool calls whose turn ended before they reached the executor. Held here
     * rather than on the entry because an entry is rebuilt whenever a snapshot
     * re-creates the call, and this is the one reason to skip that no later
     * snapshot carries.
     */
    private readonly _discardedToolCallIds;
    private readonly _settledResolvers;
    private _statuses;
    private _ac;
    private _pendingRestore;
    /** Cached last snapshot, used to skip processing on identical re-renders. */
    private _lastSnapshot;
    private _isRunning;
    private _controller;
    /**
     * Set when the assistant-stream pipeline has died (errored out via
     * `.pipeTo(...).catch(...)`). The next `setState` re-initializes the
     * pipeline and demotes each active entry that reached the executor to
     * restored, so it survives the restart without re-firing `streamCall`.
     * A restart is an execution boundary like `reset()`: an entry that had
     * not reached it starts over and fires once there (F.4). Capped at a
     * single auto-restart per session — repeated failures keep the tracker
     * dead with a more visible error.
     */
    private _pipelineDead;
    private _pipelineRestartUsed;
    constructor(getTools: () => Record<string, Tool> | undefined, callbacks: ToolInvocationTracker.Callbacks, isClientToolCall?: (toolCall: ToolCallMessagePart) => boolean | undefined);
    /**
     * Build the assistant-stream pipeline. Called once from the constructor
     * and at most once again if `_pipelineDead` is set (see F.4 in
     * EDGE_CASES.md).
     */
    private _initPipeline;
    /**
     * Feed the next observed snapshot into the tracker. Called from the host
     * runtime whenever its message list / running state changes.
     */
    setState(snapshot: ToolInvocationTracker.Snapshot): void;
    /**
     * Reset the tracker so the next observed snapshot is treated as historical.
     * Clears entries and aborts any in-flight executions. Used by callers like
     * `importExternalState` to mark a freshly loaded state as restored.
     */
    reset(): void;
    /**
     * Abort any in-flight `execute()` invocations. Resolves once all of them
     * have settled (or immediately if none are running).
     *
     * `discardPending` additionally kills the calls that never reached the
     * executor, for a caller ending the turn rather than interrupting it. The
     * signal cannot reach those: they are waiting on the run to settle (A.10),
     * and the settled snapshot arrives after this installs a fresh controller.
     */
    abort(options?: {
        discardPending?: boolean;
    }): Promise<void>;
    private _endHumanRequest;
    /**
     * Resolve a pending human-input request for the given tool call. Returns
     * `true` if a pending request was resumed, `false` if the tracker has no
     * outstanding request for that id (the caller should fall back to its own
     * dispatch path).
     */
    resume(toolCallId: string, payload: unknown): boolean;
    /**
     * Returns the current tool execution status map. The returned `Map` is
     * the tracker's internal store — do not mutate it. Treat the reference
     * as a snapshot that may be replaced wholesale on the next status
     * transition.
     */
    getStatuses(): ReadonlyMap<string, ToolExecutionStatus>;
    private _getWrappedTools;
    private _captureExecution;
    private _onHumanInput;
    private _onExecutionStart;
    private _onExecutionEnd;
    private _handleResultChunk;
    private _invokeOnResult;
    private _invokeOnStatusesChange;
    private _setStatus;
    private _deleteStatus;
    private _warnProviderOwnedSkip;
    /**
     * Closing the args stream hands the call to the client executor, so it may
     * only happen once the provider can no longer speak about that call. The run
     * ending is the only universal signal for that; an adapter that reports the
     * call as client-owned has said it earlier, per call.
     */
    private _shouldCloseArgsStream;
    private _startActiveEntry;
    /**
     * Demote every active entry back to the restored phase. Used by the
     * pipeline-restart path so that, after a fresh pipeline is built, the
     * next observed snapshot does not re-fire `streamCall` for tool calls
     * that already fired pre-death. Args / hasResult tracking is preserved
     * so signature comparisons still work.
     */
    private _demoteEntriesToRestored;
    private _processArgsText;
    private _processMessages;
}
export declare namespace ToolInvocationTracker {
    type ExecutionStatus = ToolExecutionStatus;
    type Snapshot = {
        readonly messages: readonly ThreadMessage[];
        /** Whether the producing runtime is currently streaming new output. */
        readonly isRunning: boolean;
        /**
         * Whether the producing runtime is still loading historical state.
         * When `true`, every snapshot is treated as historical (no `streamCall` /
         * `execute` fires). When `false`, processing resumes as live.
         */
        readonly isLoading?: boolean;
    };
    type Callbacks = {
        /**
         * Invoked when a client-side `execute()` returns a result and the runtime
         * needs to feed it back into the conversation.
         */
        onResult: (command: AddToolResultCommand) => void;
        /**
         * Invoked whenever the per-tool-call status map changes (executing /
         * interrupt / cleared). The callback receives a fresh map; mutating the
         * argument is not supported.
         */
        onStatusesChange: (statuses: ReadonlyMap<string, ToolExecutionStatus>) => void;
    };
}