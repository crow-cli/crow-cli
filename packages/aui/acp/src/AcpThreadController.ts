import {
  fromThreadMessageLike,
  generateId,
  type AppendMessage,
  type MessageStatus,
  type RespondToToolApprovalOptions,
  type ThreadMessage,
  type ThreadMessageLike,
} from "@assistant-ui/core";
import { invokeUserCallback } from "@assistant-ui/core/internal";
import { autoAllowPermissionHandler, type AcpClientLike } from "./AcpClient";
import {
  filterPromptBlocks,
  resolvePermissionOutcome,
  stopReasonToMessageStatus,
  threadContentToAcpBlocks,
} from "./conversions";
import {
  createAcpThreadState,
  reduceAcpThreadState,
  type AcpAssistantMessage,
  type AcpThreadEvent,
  type AcpThreadMessage,
  type AcpThreadState,
  type AcpUserMessage,
} from "./acpThreadState";
import type {
  AcpConnectionState,
  AcpContentBlock,
  AcpPermissionOutcome,
  AcpPermissionRequest,
  AcpSessionUpdate,
  AcpStopReason,
} from "./types";

export type AcpPermissionsMode = "ask" | "auto-allow";

export type AcpThreadControllerOptions = {
  client: AcpClientLike;
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

/**
 * How long a burst of `session/update` frames may be held before subscribers
 * hear about it.
 *
 * An agent streams text at roughly fifty chunks a second, and a subscriber is
 * a React tree: `useSyncExternalStore` renders on the sync lane, so every
 * notification is a blocking pass over the whole thread. Notifying per chunk
 * leaves the main thread no gap to paint in, and the reply appears to arrive
 * in one piece when the turn ends — the exact opposite of streaming. Holding
 * chunks for a beat costs a tenth of a second of latency at the tail of a
 * burst and buys a render rate a browser can actually display.
 */
const SESSION_UPDATE_NOTIFY_MS = 100;

const FALLBACK_USER_STATUS = { type: "complete", reason: "unknown" } as const;

const noop = () => {};

const toError = (error: unknown): Error =>
  error instanceof Error ? error : new Error(String(error));

type PendingPermission = {
  request: AcpPermissionRequest;
  resolve: (outcome: AcpPermissionOutcome) => void;
};

/**
 * One turn the controller owes the thread: the user message it answers, the
 * abort for a prompt that has not gone out yet, and the promise that settles
 * when the agent answers it. `runs[0]` owns the reducer's run slot; the rest
 * wait behind it. A steer's prompt is sent the moment the user steers, while
 * another turn is still in flight, so its frame is on the wire early even
 * though its turn — and its assistant message — waits its place.
 */
type RunEntry = {
  userMessageId: string;
  abort: AbortController;
  sent: boolean;
  prompt: Promise<AcpStopReason> | undefined;
  /**
   * The prompt's verdict, derived once at send time so a rejection is reported
   * once even though a steered turn is awaited twice: once while it waits its
   * place, and again when the handoff gives it the run slot.
   */
  outcome: Promise<MessageStatus> | undefined;
  finish: (() => void) | undefined;
};

export class AcpThreadController implements AcpThreadControllerLike {
  private state: AcpThreadState;
  private readonly listeners = new Set<() => void>();
  private readonly pendingPermissions = new Map<string, PendingPermission>();
  private client: AcpClientLike;
  private permissionsMode: AcpPermissionsMode;
  private autoConnect: boolean;
  private restoreOnConnect: boolean;
  private onError: ((error: Error) => void) | undefined;
  private onCancel: (() => void) | undefined;
  private loadPromise: Promise<void> | undefined;
  private hasLoaded = false;
  private runToken = 0;
  private detachToken = 0;
  private permissionCounter = 0;
  private attached = false;
  private inflightPrompt: Promise<unknown> | undefined;
  private readonly runs: RunEntry[] = [];
  private startLock: Promise<void> = Promise.resolve();
  private unsubscribeSessionUpdate: (() => void) | undefined;
  private unsubscribeConnectionChange: (() => void) | undefined;
  private restorePermissionHandler: (() => void) | undefined;
  private notifyTimer: ReturnType<typeof setTimeout> | undefined;
  private lastNotifyAt = 0;

  private readonly boundOnSessionUpdate = (
    _sessionId: string,
    update: AcpSessionUpdate,
  ) => {
    this.dispatch({ type: "session-update", update });
  };

  private readonly boundOnConnectionChange = (
    connectionState: AcpConnectionState,
  ) => {
    this.dispatch(this.connectionEvent(connectionState));
  };

  private readonly boundPermissionHandler = (request: AcpPermissionRequest) =>
    this.handlePermissionRequest(request);

  constructor(options: AcpThreadControllerOptions) {
    this.client = options.client;
    this.permissionsMode = options.permissions ?? "ask";
    this.autoConnect = options.autoConnect ?? true;
    this.restoreOnConnect = options.restoreOnConnect ?? false;
    this.onError = options.onError;
    this.onCancel = options.onCancel;
    this.state = createAcpThreadState();
  }

  getState = (): AcpThreadState => this.state;

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };

  /**
   * Subscribes instead of assigning: a caller-owned `AcpClient` keeps its own
   * listeners, and a `permissionHandler` the caller configured stays in charge
   * of approvals. Whatever this replaces is restored by `detach()`.
   */
  async attach(): Promise<void> {
    if (this.attached) return;
    this.attached = true;
    this.unsubscribeSessionUpdate = this.client.subscribeSessionUpdate(
      this.boundOnSessionUpdate,
    );
    this.unsubscribeConnectionChange = this.client.subscribeConnectionChange(
      this.boundOnConnectionChange,
    );
    if (!this.client.hasConfiguredPermissionHandler) {
      const client = this.client;
      const previous = client.permissionHandler;
      this.restorePermissionHandler = () => {
        if (client.permissionHandler === this.boundPermissionHandler) {
          client.permissionHandler = previous;
        }
      };
      client.permissionHandler = this.boundPermissionHandler;
    }
    this.dispatch(this.connectionEvent(this.client.connectionState));
  }

  async detach(): Promise<void> {
    if (!this.attached) return;
    this.attached = false;
    this.unsubscribeSessionUpdate?.();
    this.unsubscribeSessionUpdate = undefined;
    this.unsubscribeConnectionChange?.();
    this.unsubscribeConnectionChange = undefined;
    this.restorePermissionHandler?.();
    this.restorePermissionHandler = undefined;
    this.runToken += 1;
    this.detachToken += 1;
    for (const entry of this.runs) entry.abort.abort();
    const wasRunning = this.state.run.type === "running";
    for (const entry of this.runs) entry.finish?.();
    this.runs.length = 0;
    await this.settlePermissions();
    if (wasRunning) {
      this.dispatch({
        type: "run-end",
        status: { type: "incomplete", reason: "cancelled" },
      });
      try {
        await this.client.cancel();
      } catch {
        // an unsendable cancel must not reject teardown
      }
    }
    this.hasLoaded = false;
  }

  async updateOptions(options: AcpThreadControllerOptions): Promise<void> {
    const clientChanged = options.client !== this.client;
    if (clientChanged) await this.detach();
    this.client = options.client;
    this.permissionsMode = options.permissions ?? "ask";
    this.autoConnect = options.autoConnect ?? true;
    this.restoreOnConnect = options.restoreOnConnect ?? false;
    this.onError = options.onError;
    this.onCancel = options.onCancel;
    if (clientChanged) await this.attach();
  }

  async load(): Promise<void> {
    if (this.loadPromise) return this.loadPromise;
    if (this.hasLoaded) return;
    this.dispatch({ type: "load-start" });
    this.loadPromise = this.doLoad().finally(() => {
      this.loadPromise = undefined;
    });
    return this.loadPromise;
  }

  async append(message: AppendMessage): Promise<void> {
    const startRun = message.startRun ?? message.role === "user";
    const userMessage = this.toUserMessage(message);
    this.dispatch({ type: "append-message", message: userMessage });
    if (!startRun) return;
    await this.enqueueRun(userMessage.id, false);
  }

  /**
   * Send now: the prompt goes out while another turn is still in flight. The
   * agent serialises it behind that turn, and the handoff in `finishRun`
   * gives it its own assistant message the moment the turn it rode behind
   * settles — a steer attaches to the in-flight turn's completion, it never
   * replaces it.
   */
  async steer(message: AppendMessage): Promise<void> {
    const userMessage = this.toUserMessage(message);
    this.dispatch({ type: "append-message", message: userMessage });
    await this.enqueueRun(userMessage.id, true);
  }

  async cancel(): Promise<void> {
    await this.cancelRun(false);
  }

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
  async switchToThread(sessionId: string): Promise<void> {
    if (this.state.sessionId === sessionId) return;
    await this.stopRunningTurn();
    this.dispatch({ type: "reset-thread" });
    this.dispatch({ type: "replay-start" });
    try {
      await this.client.loadSession(sessionId);
    } catch (error) {
      // The old transcript is already gone, so the session has to go with it:
      // keeping it would prompt into a thread the UI no longer shows.
      this.client.releaseSession();
      this.reportError(error);
    } finally {
      this.dispatch({ type: "replay-end" });
    }
  }

  /**
   * Leave the current thread for a fresh one; the agent keeps the old. The
   * new session is minted here, not on the first prompt, so the thread list
   * and the header show its id the moment the user asks for a new thread.
   */
  async switchToNewThread(): Promise<void> {
    await this.stopRunningTurn();
    this.dispatch({ type: "reset-thread" });
    this.client.releaseSession();
    await this.ensureSession();
  }

  /** Delete a thread on the agent. Deleting the live one leaves it first. */
  async deleteThread(sessionId: string): Promise<void> {
    const wasCurrent = this.state.sessionId === sessionId;
    if (wasCurrent) await this.stopRunningTurn();
    try {
      await this.client.deleteSession(sessionId);
    } catch (error) {
      // Nothing was reset, so the thread on screen is still the truth.
      this.reportError(error);
      return;
    }
    if (wasCurrent) this.dispatch({ type: "reset-thread" });
  }

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
  async setConfigOption(configId: string, value: string): Promise<void> {
    try {
      await this.client.setConfigOption(configId, value);
    } catch (error) {
      this.reportError(error);
    }
  }

  private async stopRunningTurn(): Promise<void> {
    if (this.state.run.type === "running") await this.cancelRun(true);
  }

  /**
   * End the turn in flight. A user stop drains into the steers already on the
   * wire — the agent has those frames and will answer them, so the thread
   * keeps running through them; a stop that is really a teardown (thread
   * switch, delete, detach) drops them, because their session is going away.
   */
  private async cancelRun(dropPending: boolean): Promise<void> {
    if (this.state.run.type !== "running") return;
    this.runToken += 1;
    const entry = this.runs[0];
    entry?.abort.abort();
    await this.settlePermissions();
    const cancelled = { type: "incomplete", reason: "cancelled" } as const;
    if (dropPending) {
      for (const pending of this.runs) {
        pending.abort.abort();
        pending.finish?.();
      }
      this.runs.length = 0;
      this.dispatch({ type: "run-end", status: cancelled });
    } else if (entry) {
      this.finishRun(entry, cancelled);
    } else {
      this.dispatch({ type: "run-end", status: cancelled });
    }
    await this.client.cancel();
    invokeUserCallback("acp", "onCancel", this.onCancel);
  }

  async respondToApproval(
    options: RespondToToolApprovalOptions,
  ): Promise<void> {
    const pending = this.pendingPermissions.get(options.approvalId);
    if (!pending) return;
    this.pendingPermissions.delete(options.approvalId);

    const outcome = resolvePermissionOutcome(pending.request, {
      approvalId: options.approvalId,
      approved: options.approved,
      ...(options.optionId !== undefined && { optionId: options.optionId }),
    });
    const optionId =
      outcome.outcome === "selected" ? outcome.optionId : undefined;

    this.dispatch({
      type: "permission-resolved",
      approvalId: options.approvalId,
      approved: options.approved,
      ...(optionId !== undefined && { optionId }),
      cancelled: outcome.outcome === "cancelled",
    });
    pending.resolve(outcome);
  }

  async applyExternalMessages(
    messages: readonly ThreadMessage[],
  ): Promise<void> {
    // The transcript these turns were answering is being replaced; their
    // prompts owe nothing to the one that takes its place.
    for (const entry of this.runs) {
      entry.abort.abort();
      entry.finish?.();
    }
    this.runs.length = 0;
    const converted: AcpThreadMessage[] = [];
    const seen = new Set<string>();
    let parentId: string | null = null;
    for (const message of messages) {
      if (seen.has(message.id)) continue;
      seen.add(message.id);
      converted.push(toAcpThreadMessage(message, parentId));
      parentId = message.id;
    }
    this.dispatch({
      type: "replace-messages",
      messages: converted,
      headId: parentId,
    });
  }

  async dispose(): Promise<void> {
    await this.detach();
    this.cancelScheduledNotify();
    this.listeners.clear();
    this.loadPromise = undefined;
  }

  /**
   * Reduces eagerly and notifies on a clock. `getState()` is exact the moment
   * an event lands, so a reader mid-burst never sees a stale transcript; only
   * the render is held back, and only for the one event that arrives faster
   * than a UI can use it. Anything else — a run starting or ending, a
   * permission ask, a connection move — is a moment the user is waiting on, so
   * it goes out at once and carries any held chunk with it.
   */
  private dispatch(event: AcpThreadEvent): void {
    const next = reduceAcpThreadState(this.state, event);
    if (next === this.state) return;
    this.state = next;
    if (event.type === "session-update") this.scheduleNotify();
    else this.notifyNow();
  }

  private scheduleNotify(): void {
    if (this.notifyTimer !== undefined) return;
    const wait = Math.max(
      0,
      this.lastNotifyAt + SESSION_UPDATE_NOTIFY_MS - Date.now(),
    );
    this.notifyTimer = setTimeout(() => {
      this.notifyTimer = undefined;
      this.notifyNow();
    }, wait);
  }

  private cancelScheduledNotify(): void {
    if (this.notifyTimer === undefined) return;
    clearTimeout(this.notifyTimer);
    this.notifyTimer = undefined;
  }

  private notifyNow(): void {
    this.cancelScheduledNotify();
    this.lastNotifyAt = Date.now();
    for (const listener of [...this.listeners]) {
      invokeUserCallback("acp", "subscribe", listener);
    }
  }

  private connectionEvent(connectionState: AcpConnectionState): AcpThreadEvent {
    return {
      type: "connection",
      connectionState,
      sessionId: this.client.sessionId,
      ...(this.client.agentInfo !== undefined && {
        agentInfo: this.client.agentInfo,
      }),
      ...(this.client.agentCapabilities !== undefined && {
        agentCapabilities: this.client.agentCapabilities,
      }),
      ...(this.client.modes !== undefined && {
        sessionModes: this.client.modes,
      }),
      ...(this.client.configOptions !== undefined && {
        sessionConfigOptions: this.client.configOptions,
      }),
    };
  }

  private reportError(error: unknown): void {
    invokeUserCallback("acp", "onError", this.onError, toError(error));
  }

  private droppedBlocksError(dropped: readonly AcpContentBlock[]): Error {
    const kinds = [...new Set(dropped.map((block) => block.type))].join(", ");
    return new Error(
      `The agent's promptCapabilities do not cover ${kinds}; dropped ` +
        `${dropped.length} block(s) from this prompt.`,
    );
  }

  private reportDroppedBlocks(dropped: readonly AcpContentBlock[]): void {
    this.reportError(this.droppedBlocksError(dropped));
  }

  /**
   * Connects and marks the thread ready. The transcript is not restored from
   * storage: the agent owns the conversation, and a UI that shows messages the
   * agent has no context for would silently fork it.
   */
  private async doLoad(): Promise<void> {
    if (this.autoConnect) {
      try {
        await this.client.connect();
        this.dispatch(this.connectionEvent("connected"));
        // A prompt must never race session/new: land on the agent's newest
        // thread (session/load) or mint one (session/new) before the user
        // can type, so the session id is on screen first and every update
        // of the first turn has a session to land in.
        if (this.restoreOnConnect) await this.restoreOrCreate();
      } catch (error) {
        this.dispatch(this.connectionEvent("disconnected"));
        this.reportError(error);
      }
    }
    this.hasLoaded = true;
    this.dispatch({ type: "load-ready" });
  }

  /**
   * Open the agent's newest thread for this client's cwd, or mint a session
   * when it remembers none. Both halves are capability-gated: an agent with
   * neither list nor load still gets a fresh `session/new`.
   */
  private async restoreOrCreate(): Promise<void> {
    const caps = this.client.agentCapabilities;
    if (caps?.loadSession && caps?.sessionCapabilities?.list) {
      try {
        const page = await this.client.listSessions();
        const latest = page.sessions[0];
        if (latest) await this.switchToThread(latest.sessionId);
      } catch (error) {
        this.reportError(error);
      }
    }
    await this.ensureSession();
  }

  /**
   * Mint the session now, not on the first prompt: the header shows the
   * session id before anything is sent, and `session/prompt` can never
   * outrun `session/new`.
   */
  async ensureSession(): Promise<void> {
    if (this.state.sessionId !== undefined) return;
    await this.client.connect();
    await this.client.ensureSession();
    this.dispatch(this.connectionEvent(this.client.connectionState));
  }

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
  private async settleSupersededPrompt(): Promise<void> {
    const previous = this.inflightPrompt;
    if (!previous) return;
    await previous.then(noop, noop);
    if (this.inflightPrompt === previous) this.inflightPrompt = undefined;
  }

  private async settlePermissions(): Promise<void> {
    if (this.pendingPermissions.size === 0) return;
    const pending = [...this.pendingPermissions.values()];
    this.pendingPermissions.clear();
    this.dispatch({ type: "permissions-cancelled" });
    for (const entry of pending) entry.resolve({ outcome: "cancelled" });
  }

  private handlePermissionRequest(
    request: AcpPermissionRequest,
  ): Promise<AcpPermissionOutcome> {
    if (this.permissionsMode === "auto-allow") {
      return Promise.resolve(autoAllowPermissionHandler(request));
    }
    if (this.state.run.type !== "running") {
      return Promise.resolve({ outcome: "cancelled" });
    }
    const approvalId = `acp-permission-${(this.permissionCounter += 1)}`;
    this.dispatch({ type: "permission-request", approvalId, request });
    return new Promise<AcpPermissionOutcome>((resolve) => {
      this.pendingPermissions.set(approvalId, { request, resolve });
    });
  }

  /**
   * Serializes run prologues so two concurrent replacements cannot capture the
   * same `runToken`. The lock covers the prologue up to sending the prompt, not
   * the turn itself: the loser's prompt only settles because the winner cancels
   * it, and that cancel happens inside the prologue.
   */
  private withStartLock<T>(fn: () => Promise<T>): Promise<T> {
    const result = this.startLock.then(fn, fn);
    this.startLock = result.then(noop, noop);
    return result;
  }

  /**
   * Put one turn's prompt on the wire. `session/prompt` runs with an
   * effectively infinite timeout (setTimeout's 2^31-1 ms clamp) because a turn
   * has no bounded duration; the wait ends on the answer, or on the rejection
   * the client sends its pending requests when the socket drops. The prompt is
   * chained off `connect()` because `promptCapabilities` only exist once the
   * handshake has run, and filtering before it would withhold attachments from
   * an agent that does accept them.
   */
  private sendPrompt(entry: RunEntry): void {
    const user = this.state.messagesById[entry.userMessageId];
    const blocks = threadContentToAcpBlocks([
      ...(user?.role === "user" ? user.content : []),
      ...(user?.role === "user"
        ? user.attachments.flatMap((attachment) => attachment.content ?? [])
        : []),
    ]);
    const client = this.client;
    const prompt = client.connect().then((initialized) => {
      const filtered = filterPromptBlocks(
        blocks,
        initialized.agentCapabilities?.promptCapabilities,
      );
      if (filtered.blocks.length === 0) {
        throw filtered.dropped.length > 0
          ? this.droppedBlocksError(filtered.dropped)
          : new Error("The message has no content the agent can receive.");
      }
      if (filtered.dropped.length > 0)
        this.reportDroppedBlocks(filtered.dropped);
      return client.prompt(filtered.blocks, entry.abort.signal);
    });
    entry.sent = true;
    entry.prompt = prompt;
    entry.outcome = prompt.then(
      (reason) => stopReasonToMessageStatus(reason),
      (error) => {
        // A steer can be refused, or orphaned by a teardown, long before its
        // turn comes up; deriving the verdict here keeps that rejection from
        // being an unhandled one and reports it exactly once.
        const err = toError(error);
        this.reportError(err);
        return {
          type: "incomplete",
          reason: "error",
          error: err.message,
        } satisfies MessageStatus;
      },
    );
    this.inflightPrompt = prompt;
  }

  private assistantFor(entry: RunEntry): AcpAssistantMessage {
    return {
      role: "assistant",
      id: generateId(),
      parentId: entry.userMessageId,
      createdAt: Date.now(),
      status: { type: "running" },
      content: [],
    };
  }

  /** Give the head turn its assistant message and send its prompt. */
  private startHead(): void {
    const entry = this.runs[0];
    if (!entry || entry.sent) return;
    const user = this.state.messagesById[entry.userMessageId];
    if (user?.role !== "user") {
      this.finishRun(entry, {
        type: "incomplete",
        reason: "error",
        error: "The message this turn answers is gone.",
      });
      return;
    }
    this.dispatch({ type: "run-start", message: this.assistantFor(entry) });
    this.sendPrompt(entry);
    void this.settle(entry);
  }

  /**
   * Settle one turn: its stop reason ends its assistant message and either
   * hands the run slot to the turn waiting behind it or leaves the thread
   * idle. A turn the head slot already moved on from — cancelled, superseded,
   * detached — was finished by whoever moved it, and says nothing here.
   */
  private async settle(entry: RunEntry): Promise<void> {
    if (!entry.outcome) return;
    const status = await entry.outcome;
    if (this.inflightPrompt === entry.prompt) this.inflightPrompt = undefined;
    if (this.runs[0] !== entry) return;
    await this.settlePermissions();
    this.finishRun(entry, status);
  }

  /**
   * End the head turn. The turn behind it, when there is one, begins in the
   * same step: its prompt is already on the wire if it was steered, and goes
   * out now if it waited.
   */
  private finishRun(entry: RunEntry, status: MessageStatus): void {
    const index = this.runs.indexOf(entry);
    if (index === -1) return;
    this.runs.splice(index, 1);
    entry.finish?.();
    if (index !== 0) return;
    const next = this.runs[0];
    if (next === undefined) {
      this.dispatch({ type: "run-end", status });
      return;
    }
    this.dispatch({
      type: "run-handoff",
      status,
      message: this.assistantFor(next),
    });
    if (!next.sent) this.sendPrompt(next);
    void this.settle(next);
  }

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
  private async enqueueRun(
    userMessageId: string,
    immediate: boolean,
  ): Promise<void> {
    const entry: RunEntry = {
      userMessageId,
      abort: new AbortController(),
      sent: false,
      prompt: undefined,
      outcome: undefined,
      finish: undefined,
    };
    const finished = new Promise<void>((resolve) => {
      entry.finish = resolve;
    });
    // The lock covers the prologue only. Holding it through the turn would
    // keep every later send — including the one that supersedes this turn —
    // out until the agent answers, and the agent only answers the turn this
    // entry is waiting behind.
    const started = await this.withStartLock(() =>
      this.claimRun(entry, immediate),
    );
    if (!started) {
      entry.finish?.();
      return;
    }
    await finished;
  }

  private async claimRun(
    entry: RunEntry,
    immediate: boolean,
  ): Promise<boolean> {
    const attached = this.detachToken;
    if (!immediate) {
      if (this.state.run.type === "running") await this.cancel();
      await this.settleSupersededPrompt();
    }
    if (attached !== this.detachToken) return false;
    const user = this.state.messagesById[entry.userMessageId];
    if (user?.role !== "user") return false;
    this.runs.push(entry);
    if (this.state.run.type !== "running") this.startHead();
    else if (immediate) {
      // A steer behind a turn in flight: the frame goes out now, the run slot
      // waits for the handoff in `finishRun`.
      this.sendPrompt(entry);
      void this.settle(entry);
    }
    return true;
  }

  private toUserMessage(message: AppendMessage): AcpUserMessage {
    const requestedParent = message.parentId;
    const parentId =
      requestedParent === null
        ? null
        : requestedParent && this.state.messagesById[requestedParent]
          ? requestedParent
          : this.state.headId;
    const threadMessage = fromThreadMessageLike(
      message as ThreadMessageLike,
      generateId(),
      FALLBACK_USER_STATUS,
    );
    return {
      role: "user",
      id: threadMessage.id,
      parentId,
      createdAt: threadMessage.createdAt.getTime(),
      content:
        threadMessage.role === "user"
          ? (threadMessage.content as AcpUserMessage["content"])
          : [],
      attachments:
        threadMessage.role === "user" ? threadMessage.attachments : [],
    };
  }
}

const toAcpThreadMessage = (
  message: ThreadMessage,
  parentId: string | null,
): AcpThreadMessage => {
  const createdAt = message.createdAt.getTime();
  if (message.role === "assistant") {
    return {
      role: "assistant",
      id: message.id,
      parentId,
      createdAt,
      status: message.status,
      content: message.content,
    };
  }
  return {
    role: "user",
    id: message.id,
    parentId,
    createdAt,
    content: message.role === "user" ? message.content : [],
    attachments: message.role === "user" ? message.attachments : [],
  };
};
