import { type AcpAgentCapabilities, type AcpConnectionState, type AcpContentBlock, type AcpImplementation, type AcpInitializeResponse, type AcpMcpServer, type AcpPermissionOutcome, type AcpPermissionRequest, type AcpSessionConfigOption, type AcpSessionListResult, type AcpSessionModeState, type AcpSessionUpdate, type AcpStopReason } from "./types.js";
export type AcpWebSocketLike = {
    send(data: string): void;
    close(code?: number, reason?: string): void;
    onopen: ((event?: unknown) => void) | null;
    onmessage: ((event: {
        data: unknown;
    }) => void) | null;
    onclose: ((event?: {
        code?: number;
        reason?: string;
    }) => void) | null;
    onerror: ((event?: unknown) => void) | null;
};
export type AcpWebSocketFactory = (url: string) => AcpWebSocketLike;
export type AcpPermissionHandler = (request: AcpPermissionRequest) => AcpPermissionOutcome | Promise<AcpPermissionOutcome>;
export type AcpSessionUpdateListener = (sessionId: string, update: AcpSessionUpdate) => void;
export type AcpConnectionListener = (state: AcpConnectionState) => void;
export type AcpClientOptions = {
    /** WebSocket endpoint of the ACP agent, e.g. `ws://127.0.0.1:2770/`. */
    url: string;
    /**
     * Working directory passed to `session/new`. ACP requires an absolute path;
     * defaults to `"/"`. Set this when the agent's file tools should be rooted
     * somewhere specific.
     */
    cwd?: string;
    /** MCP servers passed to `session/new`. */
    mcpServers?: readonly AcpMcpServer[];
    /** Client identity for the `initialize` handshake. */
    clientInfo?: AcpImplementation;
    /** Inject a WebSocket implementation (tests / custom transports). */
    webSocketFactory?: AcpWebSocketFactory;
    /**
     * Reply deadline for lifecycle requests, in milliseconds. `session/prompt`
     * is exempt because a turn has no bounded duration.
     */
    requestTimeoutMs?: number;
    /**
     * Answers `session/request_permission`. Defaults to
     * `cancelPermissionHandler`, which refuses every request: an agent must
     * never be allowed to act on a decision the caller did not configure.
     */
    permissionHandler?: AcpPermissionHandler;
};
type JsonRpcId = number | string;
export declare class AcpError extends Error {
    readonly code: number;
    readonly data: unknown;
    constructor(message: string, code: number, data?: unknown);
}
export declare const autoAllowPermissionHandler: AcpPermissionHandler;
export declare const cancelPermissionHandler: AcpPermissionHandler;
export declare class AcpClient {
    private readonly options;
    private ws;
    private nextId;
    private readonly pending;
    private readonly pendingPermissions;
    private connectPromise;
    private failHandshake;
    private sessionPromise;
    private initializeResult;
    private _sessionId;
    private _connectionState;
    private _permissionHandler;
    private disposed;
    private cancelSent;
    private lostSessionId;
    private loadingSessionId;
    private sessionModes;
    private sessionConfigOptions;
    private readonly explicitPermissionHandler;
    private readonly sessionUpdateListeners;
    private readonly connectionListeners;
    constructor(options: AcpClientOptions);
    subscribeSessionUpdate(listener: AcpSessionUpdateListener): () => void;
    subscribeConnectionChange(listener: AcpConnectionListener): () => void;
    /** Whether the caller supplied `permissionHandler` in the client options. */
    get hasConfiguredPermissionHandler(): boolean;
    get connectionState(): AcpConnectionState;
    get sessionId(): string | undefined;
    get agentInfo(): AcpImplementation | undefined;
    get agentCapabilities(): AcpAgentCapabilities | undefined;
    /** Initial mode state reported by `session/new` or `session/load`. */
    get modes(): AcpSessionModeState | undefined;
    /** Initial config options reported by `session/new` or `session/load`. */
    get configOptions(): readonly AcpSessionConfigOption[] | undefined;
    get permissionHandler(): AcpPermissionHandler;
    set permissionHandler(handler: AcpPermissionHandler);
    connect(): Promise<AcpInitializeResponse>;
    ensureSession(): Promise<string>;
    /**
     * The threads the agent remembers, one page at a time: `cwd` scopes the
     * list (an agent may answer with nothing without it) and `nextCursor`
     * continues where the page stopped. An unscoped ask defaults to the
     * client's own cwd — the same directory `session/new` and `session/load`
     * use — so a bare `listSessions()` never returns another project's threads.
     */
    listSessions(options?: {
        cwd?: string;
        cursor?: string;
    }): Promise<AcpSessionListResult>;
    /**
     * Point this client at an existing thread. An agent that implements replay
     * streams the transcript as `session/update` notifications BEFORE it
     * answers, so a caller that still shows another thread's messages resets
     * them first — unlike `reloadSession`, which fences the replay out because
     * a reconnect restores a transcript the thread state already holds.
     */
    loadSession(sessionId: string): Promise<string>;
    /**
     * Delete a thread on the agent. Deleting the live session also drops it
     * here, so the next `ensureSession` mints a fresh one instead of prompting
     * into a thread the agent no longer has.
     *
     * `session/delete` is optional, and an agent that skips it still answers
     * `{}` — byte for byte a successful delete — so the thread reads as gone
     * while the agent keeps listing it. The capability check turns that silence
     * into a refusal the caller can report.
     */
    deleteSession(sessionId: string): Promise<void>;
    /**
     * Change one of the session's config options — for crow-cli that is the
     * model picker.
     *
     * ACP v1 advertises no capability for `session/set_config_option`, and an
     * agent that ignores the method still answers `{}` — byte for byte a
     * successful change. The option list a session reported IS the capability,
     * so an id the agent never advertised is refused here rather than sent,
     * exactly like `deleteSession` gates on `sessionCapabilities.delete`.
     *
     * The agent answers with the whole option array, which becomes the new
     * truth: no `config_option_update` follows a client-initiated change, so
     * the connection change emitted here is what carries the new list to
     * subscribers.
     */
    setConfigOption(configId: string, value: string): Promise<readonly AcpSessionConfigOption[]>;
    /**
     * Leave the current session without deleting it: the agent keeps the
     * thread for `session/list`, and the next `ensureSession` starts a new
     * one. Modes and config options are per-session, so they go too.
     */
    releaseSession(): void;
    /**
     * Sends `session/prompt`. An aborted `signal` cancels the turn before it is
     * sent, including while `session/new` or `session/load` is still in flight:
     * an agent must never run a turn the user already stopped.
     */
    prompt(content: readonly AcpContentBlock[], signal?: AbortSignal): Promise<AcpStopReason>;
    cancel(): Promise<void>;
    respondPermission(requestId: JsonRpcId, outcome: AcpPermissionOutcome): void;
    dispose(): void;
    private emitConnectionChange;
    private setConnectionState;
    /**
     * Drops session data and reports `"disconnected"`. Notifies only when something
     * observable changed, so a handshake failure followed by `onclose` — or a
     * `dispose()` that interrupted one — reports it exactly once.
     */
    private notifyDisconnected;
    private settlePermissions;
    private doConnect;
    private doNewSession;
    /**
     * A dropped connection leaves the agent without the transcript the UI still
     * shows, so a reconnect must not quietly continue it. `session/load` restores
     * the session when the agent advertises it; otherwise the caller gets an
     * error it can turn into a "start a new thread" prompt. The lost id survives a
     * failed attempt, so every later one keeps refusing instead of forking.
     *
     * The agent answers `session/load` only after replaying the whole transcript
     * as `session/update` notifications. That replay is history the thread state
     * already holds, so it is dropped instead of streaming into the next reply.
     * A load that fails or times out leaves that fence down: the socket is still
     * open, the agent may still be replaying, and the session stays unusable
     * either way, so a late replay must not reach the thread.
     */
    private reloadSession;
    private handleClose;
    private failPending;
    private handleMessage;
    private handleServerRequest;
    private handlePermissionRequest;
    private handleNotification;
    private request;
    private sendNotification;
    private sendRaw;
}
export {};