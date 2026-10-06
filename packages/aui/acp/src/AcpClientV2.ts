import { invokeUserCallback } from "@assistant-ui/core/internal";
import {
  AcpError,
  cancelPermissionHandler,
  type AcpClientLike,
  type AcpClientOptions,
  type AcpConnectionListener,
  type AcpPermissionHandler,
  type AcpSessionUpdateListener,
  type AcpWebSocketFactory,
  type AcpWebSocketLike,
} from "./AcpClient";
import type {
  AcpAgentCapabilities,
  AcpConnectionState,
  AcpContentBlock,
  AcpImplementation,
  AcpInitializeResponse,
  AcpMcpServer,
  AcpSessionConfigOption,
  AcpSessionListResult,
  AcpSessionModeState,
  AcpSessionUpdate,
  AcpStopReason,
} from "./types";
import type * as v2 from "./v2";

// v2 negotiates a different protocol number over the same JSON-RPC transport.
const ACP_V2_PROTOCOL_VERSION = 2;

// The vendored acp package is consumed as source (no bundler `define`), so the
// build-time version token does not exist; send the package version.
const ACP_CLIENT_VERSION = "0.1.0";

const DEFAULT_REQUEST_TIMEOUT_MS = 30_000;

const defaultWebSocketFactory: AcpWebSocketFactory = (url) =>
  new WebSocket(url) as unknown as AcpWebSocketLike;

const toError = (error: unknown): Error =>
  error instanceof Error ? error : new Error(String(error));

/** A `session/new` / `session/resume` answer, mapped into the v1 shape the
 * controller already reads. v2 has no `modes`; that stays undefined. */
type AcpV2SessionResponse = {
  sessionId: string;
  configOptions?: readonly AcpSessionConfigOption[] | undefined;
};

type JsonRpcId = number | string;

type PendingRequest = {
  resolve: (result: any) => void;
  reject: (error: Error) => void;
  timer: ReturnType<typeof setTimeout> | undefined;
};

type PromptWaiter = {
  resolve: (reason: AcpStopReason) => void;
  reject: (error: Error) => void;
};

/**
 * v2 `InitializeResponse.info` is the v1 `agentInfo`; v2 `capabilities` nest
 * everything under `session` where v1 kept flat `loadSession`/`promptCapabilities`/
 * `sessionCapabilities`. This maps the v2 surface onto the v1-shaped
 * `AcpAgentCapabilities` the controller and `filterPromptBlocks` already read.
 */
function mapAgentCapabilities(
  raw: v2.AgentCapabilities | undefined,
): AcpAgentCapabilities | undefined {
  if (!raw) return undefined;
  const session = raw.session;
  const prompt = session?.prompt;
  const mcp = session?.mcp;
  return {
    // v2 deleted `session/load`; `session/resume` is baseline once `session`
    // is advertised at all, so there is no separate marker to read.
    loadSession: session != null ? true : undefined,
    promptCapabilities: prompt
      ? {
          image: prompt.image != null ? true : undefined,
          audio: prompt.audio != null ? true : undefined,
          embeddedContext: prompt.embeddedContext != null ? true : undefined,
        }
      : undefined,
    mcpCapabilities: mcp
      ? { http: mcp.http != null ? true : undefined }
      : undefined,
    sessionCapabilities: session
      ? {
          list: {},
          delete: session.delete != null ? {} : undefined,
          fork: session.fork != null ? {} : undefined,
        }
      : undefined,
  };
}

function mapInitializeResponse(raw: v2.InitializeResponse): AcpInitializeResponse {
  return {
    protocolVersion: raw.protocolVersion,
    agentInfo: raw.info,
    agentCapabilities: mapAgentCapabilities(raw.capabilities),
  };
}

function mapMcpServers(
  servers: readonly AcpMcpServer[] | undefined,
): v2.McpServer[] | undefined {
  if (!servers || servers.length === 0) return undefined;
  const mapped: v2.McpServer[] = [];
  for (const server of servers) {
    if ("type" in server) {
      if (server.type === "http") {
        mapped.push({
          type: "http",
          name: server.name,
          url: server.url,
          headers: [...server.headers],
        });
      }
      // v2 has no SSE transport; crow advertises stdio + http only. Skip.
      continue;
    }
    mapped.push({
      type: "stdio",
      name: server.name,
      command: server.command,
      args: [...server.args],
      env: [...server.env],
    });
  }
  return mapped;
}

const flatSelectOptions = (
  options: v2.SessionConfigSelectOptions | undefined,
): readonly { value: string; name: string; description?: string | null }[] | undefined => {
  if (!options || options.length === 0) return undefined;
  const flat: { value: string; name: string; description?: string | null }[] = [];
  for (const item of options) {
    if ("options" in item) flat.push(...item.options);
    else flat.push(item);
  }
  return flat.map((option) => ({
    value: option.value,
    name: option.name,
    ...(option.description !== undefined && { description: option.description }),
  }));
};

function mapConfigOptions(
  raw: readonly v2.SessionConfigOption[] | undefined,
): readonly AcpSessionConfigOption[] | undefined {
  if (!raw) return undefined;
  const mapped: AcpSessionConfigOption[] = [];
  for (const option of raw) {
    const base = {
      id: option.configId,
      name: option.name,
      ...(option.description !== undefined && {
        description: option.description,
      }),
      ...(option.category !== undefined && { category: option.category }),
    };
    if (option.type === "boolean") {
      mapped.push({
        ...base,
        type: "boolean",
        currentValue: option.currentValue,
      } as unknown as AcpSessionConfigOption);
    } else if (option.type === "select") {
      const options = (option as v2.SessionConfigSelect).options;
      mapped.push({
        ...base,
        type: "select",
        currentValue: option.currentValue,
        options: flatSelectOptions(options),
      } as unknown as AcpSessionConfigOption);
    }
    // custom/unknown option types have no v1 shape to map to; skip them.
  }
  return mapped;
}

function mapListSessions(raw: v2.ListSessionsResponse): AcpSessionListResult {
  return {
    sessions: raw.sessions.map((session) => ({
      sessionId: session.sessionId,
      cwd: session.cwd,
      ...(session.title != null && { title: session.title }),
      ...(session.updatedAt != null && { updatedAt: session.updatedAt }),
      ...(session.additionalDirectories != null && {
        additionalDirectories: session.additionalDirectories,
      }),
    })),
    ...(raw.nextCursor != null && { nextCursor: raw.nextCursor }),
  };
}

const isRecord = (value: unknown): value is Record<string, unknown> =>
  value !== null && typeof value === "object" && !Array.isArray(value);

/** v1's renderer reads an execute cell's code from a fenced text content
 * block; v2 puts the cell in `rawInput.code`. Re-synthesize the block so the
 * v1-shaped downstream sees exactly what v1 would have sent. */
const fencedCodeBlock = (code: string) => ({
  type: "content",
  content: { type: "text", text: `\`\`\`python\n${code}\n\`\`\`` },
});

/** v1's renderer reads an execute cell's output + exit code from a JSON
 * envelope text block; v2 puts the same envelope in `rawOutput` as an object.
 * Re-emit it as the text block the renderer already unwraps. */
const outputEnvelopeBlock = (rawOutput: unknown) => {
  if (isRecord(rawOutput) && typeof rawOutput.output === "string") {
    return {
      type: "content",
      content: { type: "text", text: JSON.stringify(rawOutput) },
    };
  }
  return undefined;
};

/**
 * The v2 client: same JSON-RPC transport as `AcpClient`, same
 * `AcpClientLike` surface for the controller, but the v2 wire dialect.
 *
 * The one inversion that defines v2 — `session/prompt` acknowledges, it does
 * not run the turn — lives in `prompt()`: the response is only `{ messageId }`,
 * and the turn's end arrives as an idle `state_update` notification. Idle
 * edges are consumed in send order, so a steered prompt resolves on the idle
 * that ends ITS turn, not the turn it rode behind.
 */
export class AcpClientV2 implements AcpClientLike {
  private readonly options: AcpClientOptions;
  private ws: AcpWebSocketLike | undefined;
  private nextId = 1;
  private readonly pending = new Map<JsonRpcId, PendingRequest>();
  private connectPromise: Promise<AcpInitializeResponse> | undefined;
  private failHandshake: ((error: Error) => void) | undefined;
  private sessionPromise: Promise<string> | undefined;
  private initializeResult: AcpInitializeResponse | undefined;
  private _sessionId: string | undefined;
  private _connectionState: AcpConnectionState = "disconnected";
  private _permissionHandler: AcpPermissionHandler;
  private disposed = false;
  private cancelSent = false;
  private lostSessionId: string | undefined;
  private loadingSessionId: string | undefined;
  private sessionConfigOptions: readonly AcpSessionConfigOption[] | undefined;
  private readonly explicitPermissionHandler: boolean;
  private readonly sessionUpdateListeners = new Set<AcpSessionUpdateListener>();
  private readonly connectionListeners = new Set<AcpConnectionListener>();
  private readonly promptWaiters: PromptWaiter[] = [];
  /** v2's `tool_call_update` is an upsert: the create beat carries `rawInput`
   * and `kind`, later beats (completion) carry only `content`/`rawOutput`.
   * Remember the create fields so a later beat can still synthesize the
   * v1-shaped fenced-code block. */
  private readonly toolCallState = new Map<
    string,
    { rawInput?: unknown; isExecute?: boolean }
  >();

  constructor(options: AcpClientOptions) {
    this.options = options;
    this.explicitPermissionHandler = options.permissionHandler !== undefined;
    this._permissionHandler =
      options.permissionHandler ?? cancelPermissionHandler;
  }

  subscribeSessionUpdate(listener: AcpSessionUpdateListener): () => void {
    this.sessionUpdateListeners.add(listener);
    return () => {
      this.sessionUpdateListeners.delete(listener);
    };
  }

  subscribeConnectionChange(listener: AcpConnectionListener): () => void {
    this.connectionListeners.add(listener);
    return () => {
      this.connectionListeners.delete(listener);
    };
  }

  get hasConfiguredPermissionHandler(): boolean {
    return this.explicitPermissionHandler;
  }

  get connectionState(): AcpConnectionState {
    return this._connectionState;
  }

  get sessionId(): string | undefined {
    return this._sessionId;
  }

  get agentInfo(): AcpImplementation | undefined {
    return this.initializeResult?.agentInfo ?? undefined;
  }

  get agentCapabilities(): AcpAgentCapabilities | undefined {
    return this.initializeResult?.agentCapabilities;
  }

  /** v2 has no per-session mode surface; v1's `modes` stays empty. */
  get modes(): AcpSessionModeState | undefined {
    return undefined;
  }

  get configOptions(): readonly AcpSessionConfigOption[] | undefined {
    return this.sessionConfigOptions;
  }

  get permissionHandler(): AcpPermissionHandler {
    return this._permissionHandler;
  }

  set permissionHandler(handler: AcpPermissionHandler) {
    this._permissionHandler = handler;
  }

  connect(): Promise<AcpInitializeResponse> {
    if (this.disposed) {
      return Promise.reject(new Error("AcpClientV2 is disposed"));
    }
    if (this._connectionState === "connected" && this.initializeResult) {
      return Promise.resolve(this.initializeResult);
    }
    this.connectPromise ??= this.doConnect().finally(() => {
      this.connectPromise = undefined;
    });
    return this.connectPromise;
  }

  ensureSession(): Promise<string> {
    if (this._sessionId) return Promise.resolve(this._sessionId);
    this.sessionPromise ??= this.doNewSession().finally(() => {
      this.sessionPromise = undefined;
    });
    return this.sessionPromise;
  }

  async listSessions(
    options: { cwd?: string; cursor?: string } = {},
  ): Promise<AcpSessionListResult> {
    await this.connect();
    const cwd = options.cwd ?? this.options.cwd;
    const raw = await this.request<v2.ListSessionsResponse>("session/list", {
      ...(cwd !== undefined && { cwd }),
      ...(options.cursor !== undefined && { cursor: options.cursor }),
    });
    return mapListSessions(raw);
  }

  /**
   * Point this client at an existing thread. v2 renamed `session/load` to
   * `session/resume`; `replayFrom: { type: "start" }` asks for the transcript
   * the way `session/load` used to imply it. The agent streams that history
   * as `session/update` notifications BEFORE answering, so a caller showing
   * another thread's messages resets them first.
   */
  async loadSession(sessionId: string): Promise<string> {
    await this.connect();
    if (!this.agentCapabilities?.loadSession) {
      throw new Error(
        `The agent does not support session/resume, so thread ${sessionId} ` +
          `cannot be opened.`,
      );
    }
    const loaded = await this.resume(sessionId);
    this._sessionId = sessionId;
    this.lostSessionId = undefined;
    this.sessionConfigOptions = loaded.configOptions ?? undefined;
    this.emitConnectionChange();
    return sessionId;
  }

  async deleteSession(sessionId: string): Promise<void> {
    await this.connect();
    if (!this.agentCapabilities?.sessionCapabilities?.delete) {
      throw new Error(
        `The agent does not support session/delete, so thread ${sessionId} ` +
          `cannot be deleted.`,
      );
    }
    await this.request("session/delete", { sessionId });
    if (this._sessionId === sessionId) this.releaseSession();
  }

  async setConfigOption(
    configId: string,
    value: string,
  ): Promise<readonly AcpSessionConfigOption[]> {
    await this.connect();
    const sessionId = await this.ensureSession();
    const advertised = this.sessionConfigOptions ?? [];
    if (!advertised.some((option) => option.id === configId)) {
      throw new Error(
        `The agent advertises no config option "${configId}" for session ` +
          `${sessionId}, so it cannot be changed.`,
      );
    }
    // v2's request is a tagged union; crow's `model` select uses `type: "id"`.
    const raw = await this.request<v2.SetSessionConfigOptionResponse>(
      "session/set_config_option",
      { sessionId, configId, value, type: "id" },
    );
    const next = mapConfigOptions(raw.configOptions) ?? advertised;
    this.sessionConfigOptions = next;
    this.emitConnectionChange();
    return next;
  }

  releaseSession(): void {
    if (
      this._sessionId === undefined &&
      this.sessionConfigOptions === undefined
    ) {
      return;
    }
    this._sessionId = undefined;
    this.sessionPromise = undefined;
    this.sessionConfigOptions = undefined;
    this.emitConnectionChange();
  }

  /**
   * v2 `session/prompt` only acknowledges (`{ messageId }`). The turn's end is
   * the idle `state_update`, so the returned promise is settled by the idle
   * edge rather than by the request response. The waiter is registered BEFORE
   * the request goes out: the first-run unconfigured path emits its idle
   * before it answers the ack, and a waiter registered after would miss it.
   */
  async prompt(
    content: readonly AcpContentBlock[],
    signal?: AbortSignal,
  ): Promise<AcpStopReason> {
    if (signal?.aborted) return "cancelled";
    const sessionId = await this.ensureSession();
    if (signal?.aborted) return "cancelled";
    this.cancelSent = false;

    let resolveTurn!: (reason: AcpStopReason) => void;
    let rejectTurn!: (error: Error) => void;
    const turn = new Promise<AcpStopReason>((resolve, reject) => {
      resolveTurn = resolve;
      rejectTurn = reject;
    });
    const waiter: PromptWaiter = { resolve: resolveTurn, reject: rejectTurn };
    this.promptWaiters.push(waiter);

    try {
      await this.request<v2.PromptResponse>("session/prompt", {
        sessionId,
        prompt: content,
      });
    } catch (error) {
      const index = this.promptWaiters.indexOf(waiter);
      if (index !== -1) this.promptWaiters.splice(index, 1);
      rejectTurn(toError(error));
      throw error;
    }
    return turn;
  }

  async cancel(): Promise<void> {
    if (!this._sessionId || this._connectionState !== "connected") return;
    if (this.cancelSent) return;
    this.sendNotification("session/cancel", { sessionId: this._sessionId });
    this.cancelSent = true;
    // The agent drops everything in flight and queued, then confirms with a
    // single idle(cancelled). Resolve every waiter now: a steered prompt that
    // was dropped has no idle of its own coming, and waiting for one would
    // strand its run forever.
    this.settlePromptWaiters("cancelled");
  }

  dispose(): void {
    this.disposed = true;
    this.failHandshake?.(new Error("AcpClientV2 disposed"));
    const ws = this.ws;
    this.ws = undefined;
    if (ws) {
      ws.onopen = null;
      ws.onmessage = null;
      ws.onerror = null;
      ws.onclose = null;
      try {
        ws.close();
      } catch {
        // a throwing transport must not strand the cleanup below
      }
    }
    this.failPending(new Error("AcpClientV2 disposed"));
    this.rejectPromptWaiters(new Error("AcpClientV2 disposed"));
    this.connectPromise = undefined;
    this.sessionPromise = undefined;
    this.notifyDisconnected();
    this.sessionUpdateListeners.clear();
    this.connectionListeners.clear();
  }

  private emitConnectionChange() {
    for (const listener of [...this.connectionListeners]) {
      invokeUserCallback(
        "acp",
        "onConnectionChange",
        listener,
        this._connectionState,
      );
    }
  }

  private setConnectionState(state: AcpConnectionState) {
    if (this._connectionState === state) return;
    this._connectionState = state;
    this.emitConnectionChange();
  }

  private notifyDisconnected() {
    const hadSession =
      this._sessionId !== undefined || this.initializeResult !== undefined;
    if (this._sessionId !== undefined) this.lostSessionId = this._sessionId;
    this._sessionId = undefined;
    this.initializeResult = undefined;
    this.sessionConfigOptions = undefined;
    this.cancelSent = false;
    const stateChanged = this._connectionState !== "disconnected";
    this._connectionState = "disconnected";
    if (stateChanged || hadSession) this.emitConnectionChange();
  }

  private doConnect(): Promise<AcpInitializeResponse> {
    return new Promise<AcpInitializeResponse>((resolve, reject) => {
      let settled = false;
      const fail = (error: Error) => {
        if (settled) return;
        settled = true;
        this.failHandshake = undefined;
        this.notifyDisconnected();
        reject(error);
      };
      this.failHandshake = fail;
      this.setConnectionState("connecting");
      if (settled) return;

      let ws: AcpWebSocketLike;
      try {
        ws = (this.options.webSocketFactory ?? defaultWebSocketFactory)(
          this.options.url,
        );
      } catch (error) {
        fail(toError(error));
        return;
      }
      this.ws = ws;
      const isCurrent = () => this.ws === ws;

      ws.onopen = () => {
        if (!isCurrent()) return;
        void (async () => {
          try {
            const raw = await this.request<v2.InitializeResponse>(
              "initialize",
              {
                protocolVersion: ACP_V2_PROTOCOL_VERSION,
                info: this.options.clientInfo ?? {
                  name: "@assistant-ui/acp",
                  version: ACP_CLIENT_VERSION,
                },
              },
            );
            if (!isCurrent()) return;
            this.initializeResult = mapInitializeResponse(raw);
            if (settled) return;
            settled = true;
            this.failHandshake = undefined;
            this.setConnectionState("connected");
            resolve(this.initializeResult);
          } catch (error) {
            if (!isCurrent()) return;
            fail(toError(error));
            ws.close();
          }
        })();
      };
      ws.onmessage = (event) => {
        if (!isCurrent()) return;
        this.handleMessage(typeof event.data === "string" ? event.data : "");
      };
      ws.onclose = () => {
        if (!isCurrent()) return;
        this.handleClose();
        fail(new Error("ACP WebSocket closed before handshake completed"));
      };
      ws.onerror = () => {
        if (!isCurrent()) return;
        fail(
          new Error(`ACP WebSocket connection to ${this.options.url} failed`),
        );
      };
    });
  }

  private async resume(sessionId: string): Promise<AcpV2SessionResponse> {
    const raw = await this.request<v2.ResumeSessionResponse>(
      "session/resume",
      {
        sessionId,
        cwd: this.options.cwd ?? "/",
        mcpServers: mapMcpServers(this.options.mcpServers) ?? [],
        replayFrom: { type: "start" },
      },
    );
    return {
      sessionId,
      configOptions: mapConfigOptions(raw.configOptions),
    };
  }

  private async doNewSession(): Promise<string> {
    await this.connect();
    const lost = this.lostSessionId;
    if (lost !== undefined) return this.reloadSession(lost);
    const raw = await this.request<v2.NewSessionResponse>("session/new", {
      cwd: this.options.cwd ?? "/",
      mcpServers: mapMcpServers(this.options.mcpServers) ?? [],
    });
    this._sessionId = raw.sessionId;
    this.sessionConfigOptions = mapConfigOptions(raw.configOptions);
    this.emitConnectionChange();
    return raw.sessionId;
  }

  /**
   * A dropped connection leaves the agent without the transcript the UI still
   * shows. `session/resume` with `replayFrom: {type:"start"}` restores it; the
   * replay is fenced here because the thread state already holds the history.
   */
  private async reloadSession(sessionId: string): Promise<string> {
    const unusable = (reason: string) =>
      new Error(
        `The ACP connection dropped session ${sessionId} and it could not be ` +
          `restored (${reason}). Start a new thread to continue.`,
      );
    if (!this.agentCapabilities?.loadSession) {
      throw unusable("the agent does not support session/resume");
    }
    this.loadingSessionId = sessionId;
    let loaded: AcpV2SessionResponse;
    try {
      loaded = await this.resume(sessionId);
    } catch (error) {
      throw unusable(`session/resume failed: ${toError(error).message}`);
    }
    this.loadingSessionId = undefined;
    this._sessionId = sessionId;
    this.lostSessionId = undefined;
    this.sessionConfigOptions = loaded.configOptions ?? undefined;
    this.emitConnectionChange();
    return sessionId;
  }

  private handleClose(): void {
    this.failPending(new Error("ACP WebSocket connection closed"));
    this.rejectPromptWaiters(new Error("ACP WebSocket connection closed"));
    this.ws = undefined;
    this.notifyDisconnected();
  }

  private failPending(error: Error): void {
    for (const [, pending] of this.pending) {
      if (pending.timer !== undefined) clearTimeout(pending.timer);
      pending.reject(error);
    }
    this.pending.clear();
  }

  private settlePromptWaiters(reason: AcpStopReason): void {
    const waiters = this.promptWaiters.splice(0);
    for (const waiter of waiters) waiter.resolve(reason);
  }

  private rejectPromptWaiters(error: Error): void {
    const waiters = this.promptWaiters.splice(0);
    for (const waiter of waiters) waiter.reject(error);
  }

  private handleMessage(raw: string): void {
    let msg: any;
    try {
      msg = JSON.parse(raw);
    } catch {
      return;
    }
    if (!msg || typeof msg !== "object") return;

    if (typeof msg.method === "string") {
      if (msg.id !== undefined) this.handleServerRequest(msg);
      else this.handleNotification(msg);
      return;
    }

    if (msg.id === undefined) return;
    const pending = this.pending.get(msg.id);
    if (!pending) return;
    this.pending.delete(msg.id);
    if (pending.timer !== undefined) clearTimeout(pending.timer);
    if (msg.error) {
      pending.reject(
        new AcpError(
          msg.error.message ?? "ACP request failed",
          msg.error.code ?? -1,
          msg.error.data,
        ),
      );
    } else {
      pending.resolve(msg.result);
    }
  }

  private handleServerRequest(msg: any): void {
    // v2 crow sends no server requests (`session/request_permission` is gone;
    // elicitation is out of scope here). Answer every unknown method the same
    // way v1 answers its unknowns.
    this.sendRaw({
      jsonrpc: "2.0",
      id: msg.id,
      error: { code: -32601, message: `Method not supported: ${msg.method}` },
    });
  }

  private handleNotification(msg: any): void {
    if (msg.method !== "session/update") return;
    const params = msg.params as
      | { sessionId: string; update: AcpSessionUpdate }
      | undefined;
    if (!params?.update) return;
    if (params.sessionId === this.loadingSessionId) return;
    const update = this.mapSessionUpdate(params.update);
    this.consumeTurnBoundary(update);
    for (const listener of [...this.sessionUpdateListeners]) {
      invokeUserCallback(
        "acp",
        "onSessionUpdate",
        listener,
        params.sessionId,
        update,
      );
    }
  }

  /** Project execute input/output into display blocks. Protocol-native diff
   * content remains intact; shared consumers support both v1 and v2 diffs. */
  private mapSessionUpdate(update: AcpSessionUpdate): AcpSessionUpdate {
    if ((update as { sessionUpdate?: string }).sessionUpdate === "tool_call_update") {
      return this.mapToolCallUpdate(update as any) as AcpSessionUpdate;
    }
    return update;
  }

  private mapToolCallUpdate(raw: any): any {
    const id = raw.toolCallId as string | undefined;
    const previous = typeof id === "string" ? this.toolCallState.get(id) : undefined;
    const next = { ...previous };
    if (raw.rawInput !== undefined) next.rawInput = raw.rawInput;
    else if (raw.rawInput === null) next.rawInput = undefined;
    if (raw.kind === "execute" || raw.name === "execute") next.isExecute = true;
    if (typeof id === "string") this.toolCallState.set(id, next);

    const rawInput = next.rawInput;
    const code =
      next.isExecute &&
      isRecord(rawInput) &&
      typeof rawInput.code === "string" &&
      rawInput.code.length > 0
        ? rawInput.code
        : undefined;
    const envelope = outputEnvelopeBlock(raw.rawOutput);
    if (code === undefined && envelope === undefined && raw.content === undefined) {
      return raw;
    }
    const content = raw.content != null ? [...raw.content] : [];
    if (code !== undefined) content.unshift(fencedCodeBlock(code));
    if (envelope !== undefined) content.push(envelope);
    return { ...raw, content };
  }

  private consumeTurnBoundary(update: AcpSessionUpdate): void {
    if (update.sessionUpdate !== "state_update") return;
    if (update.state !== "idle") return;
    const waiter = this.promptWaiters.shift();
    if (waiter) waiter.resolve(update.stopReason ?? "end_turn");
  }

  private request<TResult>(
    method: string,
    params: unknown,
    timeoutMs: number | undefined = this.options.requestTimeoutMs ??
      DEFAULT_REQUEST_TIMEOUT_MS,
  ): Promise<TResult> {
    if (this._connectionState !== "connected" && method !== "initialize") {
      return Promise.reject(
        new Error(`Cannot send ${method}: ACP client is not connected`),
      );
    }
    const id = this.nextId++;
    return new Promise<TResult>((resolve, reject) => {
      const timer =
        timeoutMs === undefined
          ? undefined
          : setTimeout(() => {
              if (!this.pending.has(id)) return;
              this.pending.delete(id);
              reject(new Error(`ACP ${method} timed out after ${timeoutMs}ms`));
            }, timeoutMs);
      if (timer !== undefined) {
        (timer as unknown as { unref?: () => void }).unref?.();
      }
      this.pending.set(id, { resolve, reject, timer });
      try {
        this.sendRaw({ jsonrpc: "2.0", id, method, params });
      } catch (error) {
        this.pending.delete(id);
        if (timer !== undefined) clearTimeout(timer);
        reject(toError(error));
      }
    });
  }

  private sendNotification(method: string, params: unknown): void {
    this.sendRaw({ jsonrpc: "2.0", method, params });
  }

  private sendRaw(frame: unknown): void {
    this.ws?.send(JSON.stringify(frame));
  }
}
