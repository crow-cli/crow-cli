import { isErrorMessageId } from "../../utils/id.js";
import { appendToolInteraction, readToolInteractionLog } from "../../runtime/utils/tool-interactions.js";
import "../../runtime/utils/external-store-message.js";
import { getThreadRuntimeCoreIsRunning } from "../../runtime/api/thread-runtime.js";
//#region src/react/runtimes/external-store-history-copy.ts
var ExternalStoreHistoryCopy = class {
	thread;
	history;
	lastHistory;
	session = 0;
	copied = /* @__PURE__ */ new Map();
	failedIds = /* @__PURE__ */ new Set();
	interactions = /* @__PURE__ */ new Map();
	overlaid = /* @__PURE__ */ new WeakMap();
	pending = false;
	inFlight = false;
	timer;
	waiters = [];
	warned = false;
	signature(message) {
		try {
			return JSON.stringify({
				role: message.role,
				content: message.content,
				status: message.role === "assistant" ? message.status : void 0,
				metadata: message.metadata
			}) ?? message;
		} catch {
			return message;
		}
	}
	branch() {
		return (this.thread?.messages ?? []).filter((message) => !message.metadata.isOptimistic && !message.id.startsWith("__external_store_fallback_") && !isErrorMessageId(message.id) && !(message.role === "assistant" && message.status.type === "running")).map((message) => {
			const logs = this.interactions.get(message.id);
			if (!logs) return message;
			const cached = this.overlaid.get(message);
			if (cached && cached.logs.size === logs.size && [...logs].every(([id, log]) => cached.logs.get(id) === log)) return cached.message;
			const copy = {
				...message,
				content: message.content.map((part) => {
					if (part.type !== "tool-call") return part;
					const log = logs.get(part.toolCallId);
					return log ? {
						...part,
						unstable_interactions: log
					} : part;
				})
			};
			this.overlaid.set(message, {
				logs: new Map(logs),
				message: copy
			});
			return copy;
		});
	}
	seed() {
		for (const message of this.branch()) if (!this.copied.has(message.id) && !this.failedIds.has(message.id)) this.copied.set(message.id, this.signature(message));
	}
	attach(thread, history) {
		if (history !== this.lastHistory) {
			this.copied.clear();
			this.failedIds.clear();
			this.interactions.clear();
			this.overlaid = /* @__PURE__ */ new WeakMap();
			this.lastHistory = history;
			this.session += 1;
		}
		this.thread = thread;
		this.history = history;
		this.seed();
		const offStart = thread.unstable_on("runStart", () => this.seed());
		const offEnd = thread.unstable_on("runEnd", () => this.schedule());
		return () => {
			offStart();
			offEnd();
			if (this.timer !== void 0) clearTimeout(this.timer);
			this.timer = void 0;
			this.pending = false;
			const detached = /* @__PURE__ */ new Error("History copy was detached.");
			for (const waiter of this.waiters.splice(0)) waiter.reject(detached);
			this.thread = void 0;
			this.history = void 0;
		};
	}
	recordInteraction = async (options) => {
		const thread = this.thread;
		const message = thread?.messages.find((item) => item.id === options.messageId);
		const part = message?.content.find((item) => item.type === "tool-call" && item.toolCallId === options.toolCallId);
		if (!thread || !message || part?.type !== "tool-call") throw new Error("Tool call is not available.");
		const isRunning = getThreadRuntimeCoreIsRunning(thread);
		if (!isRunning) this.seed();
		let logs = this.interactions.get(message.id);
		if (!logs) {
			logs = /* @__PURE__ */ new Map();
			this.interactions.set(message.id, logs);
		}
		logs.set(options.toolCallId, appendToolInteraction(logs.get(options.toolCallId) ?? readToolInteractionLog(part.unstable_interactions), options.interaction));
		if (!isRunning) await this.schedule(true);
	};
	schedule(wait = false) {
		this.pending = true;
		const result = wait ? new Promise((resolve, reject) => {
			this.waiters.push({
				resolve,
				reject
			});
		}) : Promise.resolve();
		if (!this.inFlight && this.timer === void 0) this.timer = setTimeout(() => {
			this.timer = void 0;
			this.flush();
		}, 0);
		return result;
	}
	async flush() {
		if (!this.pending || !this.history) return;
		const history = this.history;
		const session = this.session;
		this.pending = false;
		this.inFlight = true;
		const waiters = this.waiters.splice(0);
		const branch = this.branch();
		const changed = branch.map((message) => [message.id, this.signature(message)]).filter(([id, signature]) => this.copied.get(id) !== signature);
		try {
			if (changed.length > 0) {
				await history.unstable_copy?.(branch, changed.map(([id]) => id));
				if (session === this.session) for (const [id, signature] of changed) {
					this.copied.set(id, signature);
					this.failedIds.delete(id);
				}
			}
			for (const waiter of waiters) waiter.resolve();
		} catch (error) {
			if (session === this.session) for (const [id] of changed) this.failedIds.add(id);
			if (!this.warned) {
				this.warned = true;
				console.warn("[useExternalStoreRuntime] Failed to copy history.", error);
			}
			for (const waiter of waiters) waiter.reject(error);
		} finally {
			this.inFlight = false;
			if (this.pending) this.schedule();
		}
	}
};
//#endregion
export { ExternalStoreHistoryCopy };
