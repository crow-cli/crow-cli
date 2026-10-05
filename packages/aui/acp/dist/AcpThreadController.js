import { filterPromptBlocks, resolvePermissionOutcome, stopReasonToMessageStatus, threadContentToAcpBlocks } from "./conversions.js";
import { autoAllowPermissionHandler } from "./AcpClient.js";
import { createAcpThreadState, reduceAcpThreadState } from "./acpThreadState.js";
import { invokeUserCallback } from "@assistant-ui/core/internal";
import { fromThreadMessageLike, generateId } from "@assistant-ui/core";
//#region src/AcpThreadController.ts
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
const FALLBACK_USER_STATUS = {
	type: "complete",
	reason: "unknown"
};
const noop = () => {};
const toError = (error) => error instanceof Error ? error : new Error(String(error));
var AcpThreadController = class {
	state;
	listeners = /* @__PURE__ */ new Set();
	pendingPermissions = /* @__PURE__ */ new Map();
	client;
	permissionsMode;
	autoConnect;
	restoreOnConnect;
	onError;
	onCancel;
	loadPromise;
	hasLoaded = false;
	runToken = 0;
	detachToken = 0;
	permissionCounter = 0;
	attached = false;
	inflightPrompt;
	runs = [];
	startLock = Promise.resolve();
	unsubscribeSessionUpdate;
	unsubscribeConnectionChange;
	restorePermissionHandler;
	notifyTimer;
	lastNotifyAt = 0;
	boundOnSessionUpdate = (_sessionId, update) => {
		this.dispatch({
			type: "session-update",
			update
		});
	};
	boundOnConnectionChange = (connectionState) => {
		this.dispatch(this.connectionEvent(connectionState));
	};
	boundPermissionHandler = (request) => this.handlePermissionRequest(request);
	constructor(options) {
		this.client = options.client;
		this.permissionsMode = options.permissions ?? "ask";
		this.autoConnect = options.autoConnect ?? true;
		this.restoreOnConnect = options.restoreOnConnect ?? false;
		this.onError = options.onError;
		this.onCancel = options.onCancel;
		this.state = createAcpThreadState();
	}
	getState = () => this.state;
	subscribe = (listener) => {
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
	async attach() {
		if (this.attached) return;
		this.attached = true;
		this.unsubscribeSessionUpdate = this.client.subscribeSessionUpdate(this.boundOnSessionUpdate);
		this.unsubscribeConnectionChange = this.client.subscribeConnectionChange(this.boundOnConnectionChange);
		if (!this.client.hasConfiguredPermissionHandler) {
			const client = this.client;
			const previous = client.permissionHandler;
			this.restorePermissionHandler = () => {
				if (client.permissionHandler === this.boundPermissionHandler) client.permissionHandler = previous;
			};
			client.permissionHandler = this.boundPermissionHandler;
		}
		this.dispatch(this.connectionEvent(this.client.connectionState));
	}
	async detach() {
		if (!this.attached) return;
		this.attached = false;
		this.unsubscribeSessionUpdate?.();
		this.unsubscribeSessionUpdate = void 0;
		this.unsubscribeConnectionChange?.();
		this.unsubscribeConnectionChange = void 0;
		this.restorePermissionHandler?.();
		this.restorePermissionHandler = void 0;
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
				status: {
					type: "incomplete",
					reason: "cancelled"
				}
			});
			try {
				await this.client.cancel();
			} catch {}
		}
		this.hasLoaded = false;
	}
	async updateOptions(options) {
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
	async load() {
		if (this.loadPromise) return this.loadPromise;
		if (this.hasLoaded) return;
		this.dispatch({ type: "load-start" });
		this.loadPromise = this.doLoad().finally(() => {
			this.loadPromise = void 0;
		});
		return this.loadPromise;
	}
	async append(message) {
		const startRun = message.startRun ?? message.role === "user";
		const userMessage = this.toUserMessage(message);
		this.dispatch({
			type: "append-message",
			message: userMessage
		});
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
	async steer(message) {
		const userMessage = this.toUserMessage(message);
		this.dispatch({
			type: "append-message",
			message: userMessage
		});
		await this.enqueueRun(userMessage.id, true);
	}
	async cancel() {
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
	async switchToThread(sessionId) {
		if (this.state.sessionId === sessionId) return;
		await this.stopRunningTurn();
		this.dispatch({ type: "reset-thread" });
		this.dispatch({ type: "replay-start" });
		try {
			await this.client.loadSession(sessionId);
		} catch (error) {
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
	async switchToNewThread() {
		await this.stopRunningTurn();
		this.dispatch({ type: "reset-thread" });
		this.client.releaseSession();
		await this.ensureSession();
	}
	/** Delete a thread on the agent. Deleting the live one leaves it first. */
	async deleteThread(sessionId) {
		const wasCurrent = this.state.sessionId === sessionId;
		if (wasCurrent) await this.stopRunningTurn();
		try {
			await this.client.deleteSession(sessionId);
		} catch (error) {
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
	async setConfigOption(configId, value) {
		try {
			await this.client.setConfigOption(configId, value);
		} catch (error) {
			this.reportError(error);
		}
	}
	async stopRunningTurn() {
		if (this.state.run.type === "running") await this.cancelRun(true);
	}
	/**
	* End the turn in flight. A user stop drains into the steers already on the
	* wire — the agent has those frames and will answer them, so the thread
	* keeps running through them; a stop that is really a teardown (thread
	* switch, delete, detach) drops them, because their session is going away.
	*/
	async cancelRun(dropPending) {
		if (this.state.run.type !== "running") return;
		this.runToken += 1;
		const entry = this.runs[0];
		entry?.abort.abort();
		await this.settlePermissions();
		const cancelled = {
			type: "incomplete",
			reason: "cancelled"
		};
		if (dropPending) {
			for (const pending of this.runs) {
				pending.abort.abort();
				pending.finish?.();
			}
			this.runs.length = 0;
			this.dispatch({
				type: "run-end",
				status: cancelled
			});
		} else if (entry) this.finishRun(entry, cancelled);
		else this.dispatch({
			type: "run-end",
			status: cancelled
		});
		await this.client.cancel();
		invokeUserCallback("acp", "onCancel", this.onCancel);
	}
	async respondToApproval(options) {
		const pending = this.pendingPermissions.get(options.approvalId);
		if (!pending) return;
		this.pendingPermissions.delete(options.approvalId);
		const outcome = resolvePermissionOutcome(pending.request, {
			approvalId: options.approvalId,
			approved: options.approved,
			...options.optionId !== void 0 && { optionId: options.optionId }
		});
		const optionId = outcome.outcome === "selected" ? outcome.optionId : void 0;
		this.dispatch({
			type: "permission-resolved",
			approvalId: options.approvalId,
			approved: options.approved,
			...optionId !== void 0 && { optionId },
			cancelled: outcome.outcome === "cancelled"
		});
		pending.resolve(outcome);
	}
	async applyExternalMessages(messages) {
		for (const entry of this.runs) {
			entry.abort.abort();
			entry.finish?.();
		}
		this.runs.length = 0;
		const converted = [];
		const seen = /* @__PURE__ */ new Set();
		let parentId = null;
		for (const message of messages) {
			if (seen.has(message.id)) continue;
			seen.add(message.id);
			converted.push(toAcpThreadMessage(message, parentId));
			parentId = message.id;
		}
		this.dispatch({
			type: "replace-messages",
			messages: converted,
			headId: parentId
		});
	}
	async dispose() {
		await this.detach();
		this.cancelScheduledNotify();
		this.listeners.clear();
		this.loadPromise = void 0;
	}
	/**
	* Reduces eagerly and notifies on a clock. `getState()` is exact the moment
	* an event lands, so a reader mid-burst never sees a stale transcript; only
	* the render is held back, and only for the one event that arrives faster
	* than a UI can use it. Anything else — a run starting or ending, a
	* permission ask, a connection move — is a moment the user is waiting on, so
	* it goes out at once and carries any held chunk with it.
	*/
	dispatch(event) {
		const next = reduceAcpThreadState(this.state, event);
		if (next === this.state) return;
		this.state = next;
		if (event.type === "session-update") this.scheduleNotify();
		else this.notifyNow();
	}
	scheduleNotify() {
		if (this.notifyTimer !== void 0) return;
		const wait = Math.max(0, this.lastNotifyAt + SESSION_UPDATE_NOTIFY_MS - Date.now());
		this.notifyTimer = setTimeout(() => {
			this.notifyTimer = void 0;
			this.notifyNow();
		}, wait);
	}
	cancelScheduledNotify() {
		if (this.notifyTimer === void 0) return;
		clearTimeout(this.notifyTimer);
		this.notifyTimer = void 0;
	}
	notifyNow() {
		this.cancelScheduledNotify();
		this.lastNotifyAt = Date.now();
		for (const listener of [...this.listeners]) invokeUserCallback("acp", "subscribe", listener);
	}
	connectionEvent(connectionState) {
		return {
			type: "connection",
			connectionState,
			sessionId: this.client.sessionId,
			...this.client.agentInfo !== void 0 && { agentInfo: this.client.agentInfo },
			...this.client.agentCapabilities !== void 0 && { agentCapabilities: this.client.agentCapabilities },
			...this.client.modes !== void 0 && { sessionModes: this.client.modes },
			...this.client.configOptions !== void 0 && { sessionConfigOptions: this.client.configOptions }
		};
	}
	reportError(error) {
		invokeUserCallback("acp", "onError", this.onError, toError(error));
	}
	droppedBlocksError(dropped) {
		const kinds = [...new Set(dropped.map((block) => block.type))].join(", ");
		return /* @__PURE__ */ new Error(`The agent's promptCapabilities do not cover ${kinds}; dropped ${dropped.length} block(s) from this prompt.`);
	}
	reportDroppedBlocks(dropped) {
		this.reportError(this.droppedBlocksError(dropped));
	}
	/**
	* Connects and marks the thread ready. The transcript is not restored from
	* storage: the agent owns the conversation, and a UI that shows messages the
	* agent has no context for would silently fork it.
	*/
	async doLoad() {
		if (this.autoConnect) try {
			await this.client.connect();
			this.dispatch(this.connectionEvent("connected"));
			if (this.restoreOnConnect) await this.restoreOrCreate();
		} catch (error) {
			this.dispatch(this.connectionEvent("disconnected"));
			this.reportError(error);
		}
		this.hasLoaded = true;
		this.dispatch({ type: "load-ready" });
	}
	/**
	* Open the agent's newest thread for this client's cwd, or mint a session
	* when it remembers none. Both halves are capability-gated: an agent with
	* neither list nor load still gets a fresh `session/new`.
	*/
	async restoreOrCreate() {
		const caps = this.client.agentCapabilities;
		if (caps?.loadSession && caps?.sessionCapabilities?.list) try {
			const latest = (await this.client.listSessions()).sessions[0];
			if (latest) await this.switchToThread(latest.sessionId);
		} catch (error) {
			this.reportError(error);
		}
		await this.ensureSession();
	}
	/**
	* Mint the session now, not on the first prompt: the header shows the
	* session id before anything is sent, and `session/prompt` can never
	* outrun `session/new`.
	*/
	async ensureSession() {
		if (this.state.sessionId !== void 0) return;
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
	async settleSupersededPrompt() {
		const previous = this.inflightPrompt;
		if (!previous) return;
		await previous.then(noop, noop);
		if (this.inflightPrompt === previous) this.inflightPrompt = void 0;
	}
	async settlePermissions() {
		if (this.pendingPermissions.size === 0) return;
		const pending = [...this.pendingPermissions.values()];
		this.pendingPermissions.clear();
		this.dispatch({ type: "permissions-cancelled" });
		for (const entry of pending) entry.resolve({ outcome: "cancelled" });
	}
	handlePermissionRequest(request) {
		if (this.permissionsMode === "auto-allow") return Promise.resolve(autoAllowPermissionHandler(request));
		if (this.state.run.type !== "running") return Promise.resolve({ outcome: "cancelled" });
		const approvalId = `acp-permission-${this.permissionCounter += 1}`;
		this.dispatch({
			type: "permission-request",
			approvalId,
			request
		});
		return new Promise((resolve) => {
			this.pendingPermissions.set(approvalId, {
				request,
				resolve
			});
		});
	}
	/**
	* Serializes run prologues so two concurrent replacements cannot capture the
	* same `runToken`. The lock covers the prologue up to sending the prompt, not
	* the turn itself: the loser's prompt only settles because the winner cancels
	* it, and that cancel happens inside the prologue.
	*/
	withStartLock(fn) {
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
	sendPrompt(entry) {
		const user = this.state.messagesById[entry.userMessageId];
		const blocks = threadContentToAcpBlocks([...user?.role === "user" ? user.content : [], ...user?.role === "user" ? user.attachments.flatMap((attachment) => attachment.content ?? []) : []]);
		const client = this.client;
		const prompt = client.connect().then((initialized) => {
			const filtered = filterPromptBlocks(blocks, initialized.agentCapabilities?.promptCapabilities);
			if (filtered.blocks.length === 0) throw filtered.dropped.length > 0 ? this.droppedBlocksError(filtered.dropped) : /* @__PURE__ */ new Error("The message has no content the agent can receive.");
			if (filtered.dropped.length > 0) this.reportDroppedBlocks(filtered.dropped);
			return client.prompt(filtered.blocks, entry.abort.signal);
		});
		entry.sent = true;
		entry.prompt = prompt;
		entry.outcome = prompt.then((reason) => stopReasonToMessageStatus(reason), (error) => {
			const err = toError(error);
			this.reportError(err);
			return {
				type: "incomplete",
				reason: "error",
				error: err.message
			};
		});
		this.inflightPrompt = prompt;
	}
	assistantFor(entry) {
		return {
			role: "assistant",
			id: generateId(),
			parentId: entry.userMessageId,
			createdAt: Date.now(),
			status: { type: "running" },
			content: []
		};
	}
	/** Give the head turn its assistant message and send its prompt. */
	startHead() {
		const entry = this.runs[0];
		if (!entry || entry.sent) return;
		if (this.state.messagesById[entry.userMessageId]?.role !== "user") {
			this.finishRun(entry, {
				type: "incomplete",
				reason: "error",
				error: "The message this turn answers is gone."
			});
			return;
		}
		this.dispatch({
			type: "run-start",
			message: this.assistantFor(entry)
		});
		this.sendPrompt(entry);
		this.settle(entry);
	}
	/**
	* Settle one turn: its stop reason ends its assistant message and either
	* hands the run slot to the turn waiting behind it or leaves the thread
	* idle. A turn the head slot already moved on from — cancelled, superseded,
	* detached — was finished by whoever moved it, and says nothing here.
	*/
	async settle(entry) {
		if (!entry.outcome) return;
		const status = await entry.outcome;
		if (this.inflightPrompt === entry.prompt) this.inflightPrompt = void 0;
		if (this.runs[0] !== entry) return;
		await this.settlePermissions();
		this.finishRun(entry, status);
	}
	/**
	* End the head turn. The turn behind it, when there is one, begins in the
	* same step: its prompt is already on the wire if it was steered, and goes
	* out now if it waited.
	*/
	finishRun(entry, status) {
		const index = this.runs.indexOf(entry);
		if (index === -1) return;
		this.runs.splice(index, 1);
		entry.finish?.();
		if (index !== 0) return;
		const next = this.runs[0];
		if (next === void 0) {
			this.dispatch({
				type: "run-end",
				status
			});
			return;
		}
		this.dispatch({
			type: "run-handoff",
			status,
			message: this.assistantFor(next)
		});
		if (!next.sent) this.sendPrompt(next);
		this.settle(next);
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
	async enqueueRun(userMessageId, immediate) {
		const entry = {
			userMessageId,
			abort: new AbortController(),
			sent: false,
			prompt: void 0,
			outcome: void 0,
			finish: void 0
		};
		const finished = new Promise((resolve) => {
			entry.finish = resolve;
		});
		if (!await this.withStartLock(() => this.claimRun(entry, immediate))) {
			entry.finish?.();
			return;
		}
		await finished;
	}
	async claimRun(entry, immediate) {
		const attached = this.detachToken;
		if (!immediate) {
			if (this.state.run.type === "running") await this.cancel();
			await this.settleSupersededPrompt();
		}
		if (attached !== this.detachToken) return false;
		if (this.state.messagesById[entry.userMessageId]?.role !== "user") return false;
		this.runs.push(entry);
		if (this.state.run.type !== "running") this.startHead();
		else if (immediate) {
			this.sendPrompt(entry);
			this.settle(entry);
		}
		return true;
	}
	toUserMessage(message) {
		const requestedParent = message.parentId;
		const parentId = requestedParent === null ? null : requestedParent && this.state.messagesById[requestedParent] ? requestedParent : this.state.headId;
		const threadMessage = fromThreadMessageLike(message, generateId(), FALLBACK_USER_STATUS);
		return {
			role: "user",
			id: threadMessage.id,
			parentId,
			createdAt: threadMessage.createdAt.getTime(),
			content: threadMessage.role === "user" ? threadMessage.content : [],
			attachments: threadMessage.role === "user" ? threadMessage.attachments : []
		};
	}
};
const toAcpThreadMessage = (message, parentId) => {
	const createdAt = message.createdAt.getTime();
	if (message.role === "assistant") return {
		role: "assistant",
		id: message.id,
		parentId,
		createdAt,
		status: message.status,
		content: message.content
	};
	return {
		role: "user",
		id: message.id,
		parentId,
		createdAt,
		content: message.role === "user" ? message.content : [],
		attachments: message.role === "user" ? message.attachments : []
	};
};
//#endregion
export { AcpThreadController };
