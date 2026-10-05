import { type AppendMessage, type RespondToToolApprovalOptions, type ThreadMessage } from "@assistant-ui/core";
import { type AcpClient } from "./AcpClient.js";
import { type AcpThreadState } from "./acpThreadState.js";
export type AcpPermissionsMode = "ask" | "auto-allow";
export type AcpThreadControllerOptions = {
    client: AcpClient;
    permissions?: AcpPermissionsMode | undefined;
    autoConnect?: boolean | undefined;
    /**
     * Land on the agent's newest thread (or mint a session when it remembers
     * none) as part of connecting, so a session id exists before the first
     * prompt and `session/prompt` can never race `session/new`.
     */
    restoreOnConnect?: boolean | undefined;
    onError?: ((error: Error) => void) | undefined;
    onCancel?: (() => void) | undefined;
};
export type AcpThreadControllerLike = {
    getState(): AcpThreadState;
    subscribe(listener: () => void): () => void;
    attach(): Promise<void>;
    detach(): Promise<void>;
    updateOptions(options: AcpThreadControllerOptions): Promise<void>;
    load(): Promise<void>;
    append(message: AppendMessage): Promise<void>;
    steer(message: AppendMessage): Promise<void>;
    cancel(): Promise<void>;
    switchToThread(sessionId: string): Promise<void>;
    switchToNewThread(): Promise<void>;
    deleteThread(sessionId: string): Promise<void>;
    setConfigOption(configId: string, value: string): Promise<void>;
    respondToApproval(options: RespondToToolApprovalOptions): Promise<void>;
    applyExternalMessages(messages: readonly ThreadMessage[]): Promise<void>;
    dispose(): Promise<void>;
};
export declare class AcpThreadController implements AcpThreadControllerLike {
    private state;
    private readonly listeners;
    private readonly pendingPermissions;
    private client;
    private permissionsMode;
    private autoConnect;
    private restoreOnConnect;
    private onError;
    private onCancel;
    private loadPromise;
    private hasLoaded;
    private runToken;
    private detachToken;
    private permissionCounter;
    private attached;
    private inflightPrompt;
    private readonly runs;
    private startLock;
    private unsubscribeSessionUpdate;
    private unsubscribeConnectionChange;
    private restorePermissionHandler;
    private notifyTimer;
    private lastNotifyAt;
    private readonly boundOnSessionUpdate;
    private readonly boundOnConnectionChange;
    private readonly boundPermissionHandler;
    constructor(options: AcpThreadControllerOptions);
    getState: () => AcpThreadState;
    subscribe: (listener: () => void) => (() => void);
    /**
     * Subscribes instead of assigning: a caller-owned `AcpClient` keeps its own
     * listeners, and a `permissionHandler` the caller configured stays in charge
     * of approvals. Whatever this replaces is restored by `detach()`.
     */
    attach(): Promise<void>;
    detach(): Promise<void>;
    updateOptions(options: AcpThreadControllerOptions): Promise<void>;
    load(): Promise<void>;
    append(message: AppendMessage): Promise<void>;
    /**
     * Send now: the prompt goes out while another turn is still in flight. The
     * agent serialises it behind that turn, and the handoff in `finishRun`
     * gives it its own assistant message the moment the turn it rode behind
     * settles — a steer attaches to the in-flight turn's completion, it never
     * replaces it.
     */
    steer(message: AppendMessage): Promise<void>;
    cancel(): Promise<void>;
    /**
     * Open another of the agent's threads. The transcript is reset BEFORE the
     * load, so whatever the agent replays lands in an empty thread instead of
     * being stitched onto the one on screen — and an agent that replays nothing
     * leaves an honest empty state.
     *
     * The replay window spans the `session/load` request itself: the agent
     * streams the transcript as `session/update` notifications and only then
     * answers, so those notifications arrive with no run in flight and would be
     * dropped unless the reducer is told a load is underway. Closing it in a
     * `finally` matters — a load that fails or times out must not leave the
     * thread accepting stray updates as history.
     */
    switchToThread(sessionId: string): Promise<void>;
    /**
     * Leave the current thread for a fresh one; the agent keeps the old. The
     * new session is minted here, not on the first prompt, so the thread list
     * and the header show its id the moment the user asks for a new thread.
     */
    switchToNewThread(): Promise<void>;
    /** Delete a thread on the agent. Deleting the live one leaves it first. */
    deleteThread(sessionId: string): Promise<void>;
    /**
     * Change one of the session's config options — the write half of
     * `useAcpConfigOptions`, and how a host moves the model picker.
     *
     * The client refuses an id the agent never advertised BEFORE sending, and
     * that refusal lands here: reported through `onError` and otherwise
     * swallowed, exactly like a delete the agent will not do. The thread state
     * only moves when the agent answers with its new option list, so a picker
     * reading `configOptions` keeps showing the value the session really has.
     */
    setConfigOption(configId: string, value: string): Promise<void>;
    private stopRunningTurn;
    /**
     * End the turn in flight. A user stop drains into the steers already on the
     * wire — the agent has those frames and will answer them, so the thread
     * keeps running through them; a stop that is really a teardown (thread
     * switch, delete, detach) drops them, because their session is going away.
     */
    private cancelRun;
    respondToApproval(options: RespondToToolApprovalOptions): Promise<void>;
    applyExternalMessages(messages: readonly ThreadMessage[]): Promise<void>;
    dispose(): Promise<void>;
    /**
     * Reduces eagerly and notifies on a clock. `getState()` is exact the moment
     * an event lands, so a reader mid-burst never sees a stale transcript; only
     * the render is held back, and only for the one event that arrives faster
     * than a UI can use it. Anything else — a run starting or ending, a
     * permission ask, a connection move — is a moment the user is waiting on, so
     * it goes out at once and carries any held chunk with it.
     */
    private dispatch;
    private scheduleNotify;
    private cancelScheduledNotify;
    private notifyNow;
    private connectionEvent;
    private reportError;
    private droppedBlocksError;
    private reportDroppedBlocks;
    /**
     * Connects and marks the thread ready. The transcript is not restored from
     * storage: the agent owns the conversation, and a UI that shows messages the
     * agent has no context for would silently fork it.
     */
    private doLoad;
    /**
     * Open the agent's newest thread for this client's cwd, or mint a session
     * when it remembers none. Both halves are capability-gated: an agent with
     * neither list nor load still gets a fresh `session/new`.
     */
    private restoreOrCreate;
    /**
     * Mint the session now, not on the first prompt: the header shows the
     * session id before anything is sent, and `session/prompt` can never
     * outrun `session/new`.
     */
    ensureSession(): Promise<void>;
    /**
     * Waits for a prompt this run superseded to settle before the next one goes
     * out. `session/update` carries no turn id, so a still-running old turn
     * would render its remaining frames inside the new assistant message. There
     * is no deadline: ACP requires an agent to answer a cancelled
     * `session/prompt` with `stopReason: "cancelled"`, and the client sends
     * `session/prompt` with an effectively infinite timeout (setTimeout's
     * 2^31-1 ms clamp) because a turn has no bounded duration. The wait
     * therefore ends on that answer, or on the rejection the client sends its
     * pending requests when the socket drops.
     */
    private settleSupersededPrompt;
    private settlePermissions;
    private handlePermissionRequest;
    /**
     * Serializes run prologues so two concurrent replacements cannot capture the
     * same `runToken`. The lock covers the prologue up to sending the prompt, not
     * the turn itself: the loser's prompt only settles because the winner cancels
     * it, and that cancel happens inside the prologue.
     */
    private withStartLock;
    /**
     * Put one turn's prompt on the wire. `session/prompt` runs with an
     * effectively infinite timeout (setTimeout's 2^31-1 ms clamp) because a turn
     * has no bounded duration; the wait ends on the answer, or on the rejection
     * the client sends its pending requests when the socket drops. The prompt is
     * chained off `connect()` because `promptCapabilities` only exist once the
     * handshake has run, and filtering before it would withhold attachments from
     * an agent that does accept them.
     */
    private sendPrompt;
    private assistantFor;
    /** Give the head turn its assistant message and send its prompt. */
    private startHead;
    /**
     * Settle one turn: its stop reason ends its assistant message and either
     * hands the run slot to the turn waiting behind it or leaves the thread
     * idle. A turn the head slot already moved on from — cancelled, superseded,
     * detached — was finished by whoever moved it, and says nothing here.
     */
    private settle;
    /**
     * End the head turn. The turn behind it, when there is one, begins in the
     * same step: its prompt is already on the wire if it was steered, and goes
     * out now if it waited.
     */
    private finishRun;
    /**
     * Queue a turn behind whatever is running. `immediate` is a steer: its
     * prompt goes out at once, even behind a turn in flight, while its run slot
     * waits its place; a plain send waits for both. A send that lands on a
     * running turn supersedes it first — the v1 contract that one append
     * replaces the turn in flight — and then waits behind any steer already on
     * the wire, because the agent answers those frames in the order they
     * arrived. A detach that lands while the prologue is waiting supersedes the
     * whole thing: the turn would otherwise be launched on a controller nobody
     * is listening to.
     */
    private enqueueRun;
    private claimRun;
    private toUserMessage;
}