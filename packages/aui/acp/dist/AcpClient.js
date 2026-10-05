import { isAllowKind } from "./conversions.js";
import "./types.js";
import { invokeUserCallback } from "@assistant-ui/core/internal";
//#region src/AcpClient.ts
var AcpError = class extends Error {
	code;
	data;
	constructor(message, code, data) {
		super(message);
		this.name = "AcpError";
		this.code = code;
		this.data = data;
	}
};
const autoAllowPermissionHandler = (request) => {
	const option = request.options.find((o) => isAllowKind(o.kind));
	return option ? {
		outcome: "selected",
		optionId: option.optionId
	} : { outcome: "cancelled" };
};
const cancelPermissionHandler = () => ({ outcome: "cancelled" });
const DEFAULT_REQUEST_TIMEOUT_MS = 3e4;
const PROMPT_TIMEOUT_MS = 2147483647;
const ACP_CLIENT_VERSION = "0.1.0";
const defaultWebSocketFactory = (url) => new WebSocket(url);
const toError = (error) => error instanceof Error ? error : new Error(String(error));
var AcpClient = class {
	options;
	ws;
	nextId = 1;
	pending = /* @__PURE__ */ new Map();
	pendingPermissions = /* @__PURE__ */ new Map();
	connectPromise;
	failHandshake;
	sessionPromise;
	initializeResult;
	_sessionId;
	_connectionState = "disconnected";
	_permissionHandler;
	disposed = false;
	cancelSent = false;
	lostSessionId;
	loadingSessionId;
	sessionModes;
	sessionConfigOptions;
	explicitPermissionHandler;
	sessionUpdateListeners = /* @__PURE__ */ new Set();
	connectionListeners = /* @__PURE__ */ new Set();
	constructor(options) {
		this.options = options;
		this.explicitPermissionHandler = options.permissionHandler !== void 0;
		this._permissionHandler = options.permissionHandler ?? cancelPermissionHandler;
	}
	subscribeSessionUpdate(listener) {
		this.sessionUpdateListeners.add(listener);
		return () => {
			this.sessionUpdateListeners.delete(listener);
		};
	}
	subscribeConnectionChange(listener) {
		this.connectionListeners.add(listener);
		return () => {
			this.connectionListeners.delete(listener);
		};
	}
	/** Whether the caller supplied `permissionHandler` in the client options. */
	get hasConfiguredPermissionHandler() {
		return this.explicitPermissionHandler;
	}
	get connectionState() {
		return this._connectionState;
	}
	get sessionId() {
		return this._sessionId;
	}
	get agentInfo() {
		return this.initializeResult?.agentInfo ?? void 0;
	}
	get agentCapabilities() {
		return this.initializeResult?.agentCapabilities;
	}
	/** Initial mode state reported by `session/new` or `session/load`. */
	get modes() {
		return this.sessionModes;
	}
	/** Initial config options reported by `session/new` or `session/load`. */
	get configOptions() {
		return this.sessionConfigOptions;
	}
	get permissionHandler() {
		return this._permissionHandler;
	}
	set permissionHandler(handler) {
		this._permissionHandler = handler;
	}
	connect() {
		if (this.disposed) return Promise.reject(/* @__PURE__ */ new Error("AcpClient is disposed"));
		if (this._connectionState === "connected" && this.initializeResult) return Promise.resolve(this.initializeResult);
		this.connectPromise ??= this.doConnect().finally(() => {
			this.connectPromise = void 0;
		});
		return this.connectPromise;
	}
	ensureSession() {
		if (this._sessionId) return Promise.resolve(this._sessionId);
		this.sessionPromise ??= this.doNewSession().finally(() => {
			this.sessionPromise = void 0;
		});
		return this.sessionPromise;
	}
	/**
	* The threads the agent remembers, one page at a time: `cwd` scopes the
	* list (an agent may answer with nothing without it) and `nextCursor`
	* continues where the page stopped. An unscoped ask defaults to the
	* client's own cwd — the same directory `session/new` and `session/load`
	* use — so a bare `listSessions()` never returns another project's threads.
	*/
	async listSessions(options = {}) {
		await this.connect();
		const cwd = options.cwd ?? this.options.cwd;
		return this.request("session/list", {
			...cwd !== void 0 && { cwd },
			...options.cursor !== void 0 && { cursor: options.cursor }
		});
	}
	/**
	* Point this client at an existing thread. An agent that implements replay
	* streams the transcript as `session/update` notifications BEFORE it
	* answers, so a caller that still shows another thread's messages resets
	* them first — unlike `reloadSession`, which fences the replay out because
	* a reconnect restores a transcript the thread state already holds.
	*/
	async loadSession(sessionId) {
		await this.connect();
		if (!this.agentCapabilities?.loadSession) throw new Error(`The agent does not support session/load, so thread ${sessionId} cannot be opened.`);
		const loaded = await this.request("session/load", {
			sessionId,
			cwd: this.options.cwd ?? "/",
			mcpServers: this.options.mcpServers ?? []
		});
		this._sessionId = sessionId;
		this.lostSessionId = void 0;
		this.sessionModes = loaded.modes ?? void 0;
		this.sessionConfigOptions = loaded.configOptions ?? void 0;
		this.emitConnectionChange();
		return sessionId;
	}
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
	async deleteSession(sessionId) {
		await this.connect();
		if (!this.agentCapabilities?.sessionCapabilities?.delete) throw new Error(`The agent does not support session/delete, so thread ${sessionId} cannot be deleted.`);
		await this.request("session/delete", { sessionId });
		if (this._sessionId === sessionId) this.releaseSession();
	}
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
	async setConfigOption(configId, value) {
		await this.connect();
		const sessionId = await this.ensureSession();
		const advertised = this.sessionConfigOptions ?? [];
		if (!advertised.some((option) => option.id === configId)) throw new Error(`The agent advertises no config option "${configId}" for session ${sessionId}, so it cannot be changed.`);
		const result = await this.request("session/set_config_option", {
			sessionId,
			configId,
			value
		});
		const next = result.configOptions ?? advertised;
		if (result.configOptions !== void 0) {
			this.sessionConfigOptions = next;
			this.emitConnectionChange();
		}
		return next;
	}
	/**
	* Leave the current session without deleting it: the agent keeps the
	* thread for `session/list`, and the next `ensureSession` starts a new
	* one. Modes and config options are per-session, so they go too.
	*/
	releaseSession() {
		if (this._sessionId === void 0 && this.sessionModes === void 0 && this.sessionConfigOptions === void 0) return;
		this._sessionId = void 0;
		this.sessionPromise = void 0;
		this.sessionModes = void 0;
		this.sessionConfigOptions = void 0;
		this.emitConnectionChange();
	}
	/**
	* Sends `session/prompt`. An aborted `signal` cancels the turn before it is
	* sent, including while `session/new` or `session/load` is still in flight:
	* an agent must never run a turn the user already stopped.
	*/
	async prompt(content, signal) {
		if (signal?.aborted) return "cancelled";
		const sessionId = await this.ensureSession();
		if (signal?.aborted) return "cancelled";
		this.cancelSent = false;
		return (await this.request("session/prompt", {
			sessionId,
			prompt: content
		}, PROMPT_TIMEOUT_MS)).stopReason ?? "end_turn";
	}
	async cancel() {
		this.settlePermissions({ outcome: "cancelled" });
		if (!this._sessionId || this._connectionState !== "connected") return;
		if (this.cancelSent) return;
		this.sendNotification("session/cancel", { sessionId: this._sessionId });
		this.cancelSent = true;
	}
	respondPermission(requestId, outcome) {
		const settle = this.pendingPermissions.get(requestId);
		if (settle) {
			settle(outcome);
			return;
		}
		this.sendRaw({
			jsonrpc: "2.0",
			id: requestId,
			result: { outcome }
		});
	}
	dispose() {
		this.disposed = true;
		this.settlePermissions({ outcome: "cancelled" });
		this.failHandshake?.(/* @__PURE__ */ new Error("AcpClient disposed"));
		const ws = this.ws;
		this.ws = void 0;
		if (ws) {
			ws.onopen = null;
			ws.onmessage = null;
			ws.onerror = null;
			ws.onclose = null;
			try {
				ws.close();
			} catch {}
		}
		this.failPending(/* @__PURE__ */ new Error("AcpClient disposed"));
		this.connectPromise = void 0;
		this.sessionPromise = void 0;
		this.notifyDisconnected();
		this.sessionUpdateListeners.clear();
		this.connectionListeners.clear();
	}
	emitConnectionChange() {
		for (const listener of [...this.connectionListeners]) invokeUserCallback("acp", "onConnectionChange", listener, this._connectionState);
	}
	setConnectionState(state) {
		if (this._connectionState === state) return;
		this._connectionState = state;
		this.emitConnectionChange();
	}
	/**
	* Drops session data and reports `"disconnected"`. Notifies only when something
	* observable changed, so a handshake failure followed by `onclose` — or a
	* `dispose()` that interrupted one — reports it exactly once.
	*/
	notifyDisconnected() {
		const hadSession = this._sessionId !== void 0 || this.initializeResult !== void 0;
		if (this._sessionId !== void 0) this.lostSessionId = this._sessionId;
		this._sessionId = void 0;
		this.initializeResult = void 0;
		this.sessionModes = void 0;
		this.sessionConfigOptions = void 0;
		this.cancelSent = false;
		const stateChanged = this._connectionState !== "disconnected";
		this._connectionState = "disconnected";
		if (stateChanged || hadSession) this.emitConnectionChange();
	}
	settlePermissions(outcome) {
		if (this.pendingPermissions.size === 0) return;
		const settle = [...this.pendingPermissions.values()];
		this.pendingPermissions.clear();
		for (const resolve of settle) resolve(outcome);
	}
	doConnect() {
		return new Promise((resolve, reject) => {
			let settled = false;
			const fail = (error) => {
				if (settled) return;
				settled = true;
				this.failHandshake = void 0;
				this.notifyDisconnected();
				reject(error);
			};
			this.failHandshake = fail;
			this.setConnectionState("connecting");
			if (settled) return;
			let ws;
			try {
				ws = (this.options.webSocketFactory ?? defaultWebSocketFactory)(this.options.url);
			} catch (error) {
				fail(toError(error));
				return;
			}
			this.ws = ws;
			const isCurrent = () => this.ws === ws;
			ws.onopen = () => {
				if (!isCurrent()) return;
				(async () => {
					try {
						const result = await this.request("initialize", {
							protocolVersion: 1,
							clientCapabilities: {},
							clientInfo: this.options.clientInfo ?? {
								name: "@assistant-ui/acp",
								version: ACP_CLIENT_VERSION
							}
						});
						if (!isCurrent()) return;
						this.initializeResult = result;
						if (settled) return;
						settled = true;
						this.failHandshake = void 0;
						this.setConnectionState("connected");
						resolve(result);
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
				fail(/* @__PURE__ */ new Error("ACP WebSocket closed before handshake completed"));
			};
			ws.onerror = () => {
				if (!isCurrent()) return;
				fail(/* @__PURE__ */ new Error(`ACP WebSocket connection to ${this.options.url} failed`));
			};
		});
	}
	async doNewSession() {
		await this.connect();
		const lost = this.lostSessionId;
		if (lost !== void 0) return this.reloadSession(lost);
		const result = await this.request("session/new", {
			cwd: this.options.cwd ?? "/",
			mcpServers: this.options.mcpServers ?? []
		});
		this._sessionId = result.sessionId;
		this.sessionModes = result.modes ?? void 0;
		this.sessionConfigOptions = result.configOptions ?? void 0;
		this.emitConnectionChange();
		return result.sessionId;
	}
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
	async reloadSession(sessionId) {
		const unusable = (reason) => /* @__PURE__ */ new Error(`The ACP connection dropped session ${sessionId} and it could not be restored (${reason}). Start a new thread to continue.`);
		if (!this.agentCapabilities?.loadSession) throw unusable("the agent does not support session/load");
		this.loadingSessionId = sessionId;
		let loaded;
		try {
			loaded = await this.request("session/load", {
				sessionId,
				cwd: this.options.cwd ?? "/",
				mcpServers: this.options.mcpServers ?? []
			});
		} catch (error) {
			throw unusable(`session/load failed: ${toError(error).message}`);
		}
		this.loadingSessionId = void 0;
		this._sessionId = sessionId;
		this.lostSessionId = void 0;
		this.sessionModes = loaded.modes ?? void 0;
		this.sessionConfigOptions = loaded.configOptions ?? void 0;
		this.emitConnectionChange();
		return sessionId;
	}
	handleClose() {
		this.failPending(/* @__PURE__ */ new Error("ACP WebSocket connection closed"));
		this.settlePermissions({ outcome: "cancelled" });
		this.ws = void 0;
		this.notifyDisconnected();
	}
	failPending(error) {
		for (const [, pending] of this.pending) {
			if (pending.timer !== void 0) clearTimeout(pending.timer);
			pending.reject(error);
		}
		this.pending.clear();
	}
	handleMessage(raw) {
		let msg;
		try {
			msg = JSON.parse(raw);
		} catch {
			return;
		}
		if (!msg || typeof msg !== "object") return;
		if (typeof msg.method === "string") {
			if (msg.id !== void 0) this.handleServerRequest(msg);
			else this.handleNotification(msg);
			return;
		}
		if (msg.id === void 0) return;
		const pending = this.pending.get(msg.id);
		if (!pending) return;
		this.pending.delete(msg.id);
		if (pending.timer !== void 0) clearTimeout(pending.timer);
		if (msg.error) pending.reject(new AcpError(msg.error.message ?? "ACP request failed", msg.error.code ?? -1, msg.error.data));
		else pending.resolve(msg.result);
	}
	handleServerRequest(msg) {
		if (msg.method === "session/request_permission") {
			this.handlePermissionRequest(msg.id, msg.params);
			return;
		}
		this.sendRaw({
			jsonrpc: "2.0",
			id: msg.id,
			error: {
				code: -32601,
				message: `Method not supported: ${msg.method}`
			}
		});
	}
	handlePermissionRequest(requestId, params) {
		let settled = false;
		const reply = (outcome) => {
			if (settled) return;
			settled = true;
			this.pendingPermissions.delete(requestId);
			try {
				this.sendRaw({
					jsonrpc: "2.0",
					id: requestId,
					result: { outcome }
				});
			} catch {}
		};
		this.pendingPermissions.set(requestId, reply);
		let handled;
		try {
			handled = Promise.resolve(this.permissionHandler(params));
		} catch (error) {
			invokeUserCallback("acp", "permissionHandler", () => {
				throw error;
			});
			reply({ outcome: "cancelled" });
			return;
		}
		handled.then(reply, () => reply({ outcome: "cancelled" }));
	}
	handleNotification(msg) {
		if (msg.method !== "session/update") return;
		const params = msg.params;
		if (!params?.update) return;
		if (params.sessionId === this.loadingSessionId) return;
		for (const listener of [...this.sessionUpdateListeners]) invokeUserCallback("acp", "onSessionUpdate", listener, params.sessionId, params.update);
	}
	request(method, params, timeoutMs = this.options.requestTimeoutMs ?? DEFAULT_REQUEST_TIMEOUT_MS) {
		if (this._connectionState !== "connected" && method !== "initialize") return Promise.reject(/* @__PURE__ */ new Error(`Cannot send ${method}: ACP client is not connected`));
		const id = this.nextId++;
		return new Promise((resolve, reject) => {
			const timer = timeoutMs === void 0 ? void 0 : setTimeout(() => {
				if (!this.pending.has(id)) return;
				this.pending.delete(id);
				reject(/* @__PURE__ */ new Error(`ACP ${method} timed out after ${timeoutMs}ms`));
			}, timeoutMs);
			if (timer !== void 0) timer.unref?.();
			this.pending.set(id, {
				resolve,
				reject,
				timer
			});
			try {
				this.sendRaw({
					jsonrpc: "2.0",
					id,
					method,
					params
				});
			} catch (error) {
				this.pending.delete(id);
				if (timer !== void 0) clearTimeout(timer);
				reject(toError(error));
			}
		});
	}
	sendNotification(method, params) {
		this.sendRaw({
			jsonrpc: "2.0",
			method,
			params
		});
	}
	sendRaw(frame) {
		this.ws?.send(JSON.stringify(frame));
	}
};
//#endregion
export { AcpClient, AcpError, autoAllowPermissionHandler, cancelPermissionHandler };
