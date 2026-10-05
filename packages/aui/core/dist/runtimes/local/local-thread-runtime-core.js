import { generateId } from "../../utils/id.js";
import { consumeSuggestionResult } from "../../adapters/suggestion.js";
import { MessageNotSentError, toAssistantError } from "../../types/error.js";
import { appendToolInteraction } from "../../runtime/utils/tool-interactions.js";
import { fromThreadMessageLike } from "../../runtime/utils/thread-message-like.js";
import { getAutoStatus } from "../../runtime/utils/auto-status.js";
import { withoutOrphanedMessages } from "../../runtime/utils/message-repository.js";
import { EMPTY_QUEUE_ITEMS } from "../../runtime/queue/queue-item.js";
import { createMessageQueue } from "../../runtime/queue/message-queue.js";
import { captureThreadRuntimeGeneration, invalidateThreadRuntime } from "../../runtime/utils/thread-runtime-lifecycle.js";
import { BaseThreadRuntimeCore } from "../../runtime/base/base-thread-runtime-core.js";
import { shouldContinue } from "./should-continue.js";
//#region src/runtimes/local/local-thread-runtime-core.ts
var AbortError = class extends Error {
	name = "AbortError";
	detach;
	constructor(detach, message) {
		super(message);
		this.detach = detach;
	}
};
const withLocalPauseReason = (message) => {
	if (message.role !== "assistant" || message.status.type !== "requires-action" || message.status.reason !== "interrupt" || message.content.some((c) => c.type === "tool-call" && c.result === void 0 && c.interrupt != null)) return message;
	return {
		...message,
		status: getAutoStatus(false, false, false, message.content.some((c) => c.type === "tool-call" && c.result === void 0))
	};
};
const withCancelledPause = (message) => {
	let cancelled = false;
	const content = message.content.map((part) => {
		if (part.type !== "tool-call" || part.approval === void 0 || part.approval.approved !== void 0 || part.approval.resolution !== void 0) return part;
		cancelled = true;
		return {
			...part,
			approval: {
				...part.approval,
				resolution: "cancelled"
			}
		};
	});
	const open = message.status.type === "running" || message.status.type === "requires-action";
	if (!cancelled && !open) return message;
	return {
		...message,
		content,
		status: open ? {
			type: "incomplete",
			reason: "cancelled"
		} : message.status
	};
};
const withLocalPauseReasons = (data) => {
	const followed = new Set(data.messages.map((item) => item.parentId));
	return {
		...data,
		messages: data.messages.map((item) => ({
			...item,
			message: item.message.role === "assistant" && followed.has(item.message.id) ? withCancelledPause(item.message) : withLocalPauseReason(item.message)
		}))
	};
};
const withoutToolInteractions = (message) => {
	if (message.role !== "assistant") return message;
	let hasInteractions = false;
	const content = message.content.map((part) => {
		if (part.type !== "tool-call") return part;
		const nestedMessages = part.messages?.map(withoutToolInteractions);
		const hasNestedInteractions = nestedMessages?.some((nestedMessage, index) => nestedMessage !== part.messages?.[index]);
		if (part.unstable_interactions === void 0 && hasNestedInteractions !== true) return part;
		hasInteractions = true;
		const { unstable_interactions: _, ...withoutInteractions } = part;
		return hasNestedInteractions ? {
			...withoutInteractions,
			messages: nestedMessages
		} : withoutInteractions;
	});
	return hasInteractions ? {
		...message,
		content
	} : message;
};
var LocalThreadRuntimeCore = class extends BaseThreadRuntimeCore {
	capabilities = {
		switchToBranch: true,
		switchBranchDuringRun: true,
		edit: true,
		delete: false,
		reload: true,
		refetchThread: false,
		cancel: true,
		unstable_copy: true,
		speech: false,
		dictation: false,
		voice: false,
		attachments: false,
		feedback: false,
		queue: false,
		answerToolCall: true
	};
	abortController = null;
	_queue = null;
	_queueRunInFlight = null;
	_activeRun = null;
	_runGeneration = 0;
	_messageReplacements = /* @__PURE__ */ new WeakMap();
	_historyWrites = /* @__PURE__ */ new Map();
	async _writeHistory(operation, messageIds, write) {
		try {
			await write();
		} catch (error) {
			console.error("[assistant-ui] local thread history write failed:", error);
			this._notifyEventSubscribers("historyWriteError", {
				operation,
				messageIds,
				message: error instanceof Error ? error.message : String(error),
				error
			});
			throw error;
		}
	}
	_deletedMessages = /* @__PURE__ */ new Map();
	_chainHistoryWrite(id, write) {
		const tombstone = this._deletedMessages.get(id);
		if (tombstone) {
			tombstone.suppressed?.push(write);
			return Promise.resolve();
		}
		const pending = this._historyWrites.get(id);
		let next;
		if (pending) next = pending.then(write, write);
		else try {
			next = Promise.resolve(write());
		} catch (error) {
			next = Promise.reject(error);
		}
		const stored = next.then(() => {}, () => {});
		this._historyWrites.set(id, stored);
		stored.then(() => {
			if (this._historyWrites.get(id) === stored) this._historyWrites.delete(id);
		});
		return next;
	}
	_persistMessageUpdate(messageId) {
		const history = this._options.adapters.history;
		if (!history) return;
		let entry;
		try {
			entry = this.repository.getMessage(messageId);
		} catch {
			return;
		}
		const { parentId, message } = entry;
		if (message.role !== "assistant" || message.status.type === "running") return;
		if (this._unwrittenMessages.has(message.id) && !history.update && message.status.type === "requires-action") return;
		this._persistSettled(parentId, message)?.catch(() => {});
	}
	_roundtripsInFlight = /* @__PURE__ */ new Map();
	_followedDuringRun = /* @__PURE__ */ new Set();
	_unwrittenMessages = /* @__PURE__ */ new Set();
	_persistSettled(parentId, message) {
		const history = this._options.adapters.history;
		if (!history) return;
		const operation = this._unwrittenMessages.delete(message.id) ? "append" : "update";
		const write = operation === "append" ? history.append : history.update;
		if (!write) return;
		const item = {
			parentId,
			message,
			runConfig: this._lastRunConfig
		};
		return this._chainHistoryWrite(message.id, () => this._writeHistory(operation, [message.id], () => write.call(history, item)));
	}
	_cancelPause(messageId) {
		if (messageId === null) return;
		let entry;
		try {
			entry = this.repository.getMessage(messageId);
		} catch {
			return;
		}
		if (entry.message.role !== "assistant") return;
		if (this._roundtripsInFlight.has(messageId)) {
			this._followedDuringRun.add(messageId);
			const snapshot = withCancelledPause(entry.message);
			const history = this._options.adapters.history;
			if (history && !history.update && this._roundtripsInFlight.get(messageId)?.resumedFromPause && !this._unwrittenMessages.has(messageId)) {
				const item = {
					parentId: entry.parentId,
					message: snapshot,
					runConfig: this._lastRunConfig
				};
				return this._chainHistoryWrite(messageId, () => this._writeHistory("append", [messageId], () => history.append(item)));
			}
			return this._persistSettled(entry.parentId, snapshot);
		}
		const message = withCancelledPause(entry.message);
		if (message === entry.message) return;
		this.repository.addOrUpdateMessage(entry.parentId, message);
		return this._persistSettled(entry.parentId, message);
	}
	_resumeIfReady(messageId) {
		const stored = this.getMessageById(messageId);
		if (stored?.message.role !== "assistant" || this.repository.hasChildren(messageId) || this._followedDuringRun.has(messageId) || !shouldContinue(stored.message, this._options.unstable_humanToolNames)) return false;
		this._runLoop(stored.parentId, stored.message, this._lastRunConfig).catch(() => {});
		return true;
	}
	isDisabled = false;
	isSendDisabled = false;
	_isLoading = false;
	get isLoading() {
		return this._isLoading;
	}
	_suggestions = [];
	_suggestionsController = null;
	get suggestions() {
		return this._suggestions;
	}
	get adapters() {
		return this._options.adapters;
	}
	constructor(contextProvider, options) {
		super(contextProvider);
		this.__internal_setOptions(options);
	}
	_options;
	_lastRunConfig = {};
	_getThreadId;
	__internal_setGetThreadId(getThreadId) {
		this._getThreadId = getThreadId;
	}
	_getInitializePromise;
	__internal_setGetInitializePromise(getPromise) {
		this._getInitializePromise = getPromise;
	}
	get extras() {}
	__internal_setOptions(options) {
		if (this._options === options) return;
		const previousHistory = this._options?.adapters.history;
		this._options = options;
		if (!options.adapters.voice && this.voice) try {
			this.disconnectVoice();
		} catch (error) {
			console.error("[assistant-ui] Voice cleanup threw after the adapter changed", error);
		}
		let hasUpdates = false;
		if (!options.adapters.suggestion) {
			this._suggestionsController?.abort();
			this._suggestionsController = null;
			if (this._suggestions.length > 0) {
				this._suggestions = [];
				hasUpdates = true;
			}
		}
		const canSpeak = options.adapters?.speech !== void 0;
		if (this.capabilities.speech !== canSpeak) {
			this.capabilities.speech = canSpeak;
			hasUpdates = true;
		}
		const canDictate = options.adapters?.dictation !== void 0;
		if (this.capabilities.dictation !== canDictate) {
			this.capabilities.dictation = canDictate;
			hasUpdates = true;
		}
		const canVoice = options.adapters?.voice !== void 0;
		if (this.capabilities.voice !== canVoice) {
			this.capabilities.voice = canVoice;
			hasUpdates = true;
		}
		const canAttach = options.adapters?.attachments !== void 0;
		if (this.capabilities.attachments !== canAttach) {
			this.capabilities.attachments = canAttach;
			hasUpdates = true;
		}
		const canFeedback = options.adapters?.feedback !== void 0;
		if (this.capabilities.feedback !== canFeedback) {
			this.capabilities.feedback = canFeedback;
			hasUpdates = true;
		}
		const canDelete = options.adapters?.history?.delete !== void 0;
		if (this.capabilities.delete !== canDelete) {
			this.capabilities.delete = canDelete;
			hasUpdates = true;
		}
		const canQueue = options.unstable_enableMessageQueue === true;
		if (canQueue && !this._queue) {
			this._queue = createMessageQueue({ run: (message) => {
				const dispatch = {};
				this._queueRunInFlight = dispatch;
				const generation = this._runGeneration;
				this._runAppend({
					...message,
					parentId: this._resolveAppendParent(this.messages.at(-1)?.id ?? null)
				}).finally(() => {
					if (this._queueRunInFlight === dispatch) {
						this._queueRunInFlight = null;
						if (this._runGeneration === generation) this._queue?.notifyIdle();
					}
				}).catch(() => {});
			} });
			if (this.voice) this._queue.hold();
			this._queue.subscribe(() => this._notifySubscribers());
		} else if (!canQueue && this._queue) this._queue = null;
		if (this.capabilities.queue !== canQueue) {
			this.capabilities.queue = canQueue;
			hasUpdates = true;
		}
		if (hasUpdates) this._notifySubscribers();
		if (this._loadRequested && !this._loadPromise && !previousHistory && options.adapters.history && this.messages.length === 0) this.__internal_load().catch((error) => {
			console.error("[assistant-ui] local thread history load failed:", error);
		});
	}
	_loadPromise;
	_loadRequested = false;
	__internal_load() {
		this._loadRequested = true;
		if (this._loadPromise) return this._loadPromise;
		if (!this.adapters.history) return Promise.resolve();
		const promise = this.adapters.history.load();
		this._isLoading = true;
		this._loadPromise = promise.then((repo) => {
			if (!repo) return;
			const { repository, droppedIds } = withoutOrphanedMessages(repo);
			if (droppedIds.length > 0) console.warn("[assistant-ui] Skipped history messages with missing parents:", droppedIds);
			if (repo.headId != null && !repo.messages.some((item) => item.message.id === repo.headId)) console.warn("[assistant-ui] History head is not among the loaded messages:", repo.headId);
			this.repository.import(withLocalPauseReasons(repository));
			if (repository.messages.length > 0) this.ensureInitialized();
			this._notifySubscribers();
			const resume = this.adapters.history?.resume?.bind(this.adapters.history);
			if (repo.unstable_resume && resume) this.startRun({
				parentId: this.repository.headId,
				sourceId: this.repository.headId,
				runConfig: this._lastRunConfig
			}, resume).catch(() => {});
		}).finally(() => {
			this._isLoading = false;
			this._notifySubscribers();
		});
		this._notifySubscribers();
		return this._loadPromise;
	}
	_getHistoryLoadBarrier() {
		if (!this._isLoading || !this._loadPromise) return void 0;
		return this._loadPromise.catch(() => {});
	}
	async append(message) {
		message = {
			...message,
			parentId: this._resolveAppendParent(message.parentId)
		};
		if (this.voice) return this._appendToVoiceSession(message);
		if (this._isVoiceMessage(message.sourceId)) throw new Error("Voice transcript messages cannot be edited");
		const isTail = message.parentId === (this.messages.at(-1)?.id ?? null);
		const willRun = message.startRun ?? message.role === "user";
		if (this._queue && willRun && isTail) {
			if (message.steer ?? this._queueRunInFlight !== null) this._queue.adapter.steer(message);
			else this._queue.adapter.enqueue(message);
			return;
		}
		if (this._queue && !isTail && (this._options.unstable_queueClearOnRewind ?? true)) this._queue.clear();
		return this._runAppend(message);
	}
	_commitVoiceMessage(message) {
		const generation = captureThreadRuntimeGeneration(this);
		const commit = (notify) => {
			if (generation.aborted) {
				this._dropVoiceMessage(message.id, notify);
				return;
			}
			const parentId = this.repository.headId;
			this.repository.addOrUpdateMessage(parentId, message);
			const settledWrite = this._cancelPause(parentId);
			this.repository.resetHead(message.id);
			const history = this._options.adapters.history;
			const historyWrite = history ? this._chainHistoryWrite(message.id, () => this._writeHistory("append", [message.id], () => history.append({
				parentId,
				message
			}))) : void 0;
			historyWrite?.catch(() => {});
			this._dropVoiceMessage(message.id, false);
			if (notify) this._notifySubscribers();
			return settledWrite ? Promise.all([settledWrite, historyWrite]).then(() => {}) : historyWrite;
		};
		const barrier = this._getVoiceCommitBarrier();
		return barrier ? barrier.then(() => commit(true)) : commit(false);
	}
	_onVoiceConnected() {
		this._queue?.hold();
	}
	_onVoiceDisconnected() {
		this._queue?.release();
	}
	getQueueItems() {
		return this._queue?.adapter.items ?? EMPTY_QUEUE_ITEMS;
	}
	getSteerQueueItems() {
		return this._queue?.adapter.steerItems ?? EMPTY_QUEUE_ITEMS;
	}
	moveQueueItem(queueItemId, placement) {
		this._queue?.adapter.move(queueItemId, placement);
	}
	editQueueItem(queueItemId, message) {
		this._queue?.adapter.edit(queueItemId, message);
	}
	removeQueueItem(queueItemId) {
		this._queue?.adapter.remove(queueItemId);
	}
	_rollbackAppend(messageId) {
		try {
			this.repository.deleteMessage(messageId);
		} catch {
			return;
		}
		this._notifySubscribers();
	}
	_pendingAppends = 0;
	_isRunActive() {
		return this._pendingAppends > 0 || super._isRunActive();
	}
	async _runAppend(rawMessage) {
		this._pendingAppends += 1;
		try {
			await this._runAppendInner(rawMessage);
		} finally {
			this._pendingAppends -= 1;
		}
	}
	async _runAppendInner(rawMessage) {
		const generation = captureThreadRuntimeGeneration(this);
		const loadBarrier = this._getHistoryLoadBarrier();
		if (loadBarrier) {
			const wasAtTail = rawMessage.parentId === (this.messages.at(-1)?.id ?? null);
			await loadBarrier;
			if (generation.aborted) return;
			if (wasAtTail) rawMessage = {
				...rawMessage,
				parentId: this._resolveAppendParent(this.messages.at(-1)?.id ?? null)
			};
		}
		const message = this.enrichAppendMetadata(rawMessage);
		this.ensureInitialized();
		const newMessage = fromThreadMessageLike(message, generateId(), {
			type: "complete",
			reason: "unknown"
		});
		this.repository.addOrUpdateMessage(message.parentId, newMessage);
		this._notifySubscribers();
		try {
			const initPromise = this._getInitializePromise?.();
			if (initPromise) await initPromise;
		} catch (error) {
			this._rollbackAppend(newMessage.id);
			if (generation.aborted) return;
			if (message.parentId !== null) this._resumeIfReady(message.parentId);
			const notSent = new MessageNotSentError();
			notSent.cause = error;
			throw notSent;
		}
		if (generation.aborted) {
			this._rollbackAppend(newMessage.id);
			return;
		}
		const settledWrite = this._cancelPause(message.parentId);
		const history = this._options.adapters.history;
		const messageWrite = history ? this._chainHistoryWrite(newMessage.id, () => this._writeHistory("append", [newMessage.id], () => history.append({
			parentId: message.parentId,
			message: newMessage,
			...message.runConfig !== void 0 && { runConfig: message.runConfig }
		}))) : void 0;
		const historyWrite = settledWrite ? Promise.all([settledWrite, messageWrite]).then(() => {}) : messageWrite;
		historyWrite?.catch(() => {});
		if (message.startRun ?? message.role === "user") {
			const [runResult, historyResult] = await Promise.allSettled([this.startRun({
				parentId: newMessage.id,
				sourceId: message.sourceId,
				runConfig: message.runConfig ?? {}
			}), historyWrite]);
			if (runResult.status === "rejected") throw runResult.reason;
			if (historyResult.status === "rejected") throw historyResult.reason;
		} else {
			this.repository.switchToBranch(newMessage.id);
			this._notifySubscribers();
			await historyWrite;
		}
	}
	async deleteMessage(messageId) {
		const adapter = this._options.adapters.history;
		if (!adapter?.delete) throw new Error("Runtime does not support deleting messages.");
		const messages = this.repository.getMessages();
		const messageIndex = messages.findIndex((m) => m.id === messageId);
		if (messageIndex === -1) throw new Error("Message not found.");
		const inFlight = this._deletedMessages.get(messageId);
		if (inFlight?.suppressed && inFlight.deletion) return inFlight.deletion;
		const deleteAdapter = adapter.delete.bind(adapter);
		const deleteHistory = (items) => this._writeHistory("delete", items.map((item) => item.message.id), () => deleteAdapter(items));
		const message = messages[messageIndex];
		const items = [{
			parentId: messages[messageIndex - 1]?.id ?? null,
			message
		}];
		const pending = this._historyWrites.get(messageId);
		const tombstone = { suppressed: [] };
		this._deletedMessages.set(messageId, tombstone);
		tombstone.deletion = (async () => {
			try {
				await deleteHistory(items);
			} catch (error) {
				const suppressed = tombstone.suppressed ?? [];
				tombstone.suppressed = null;
				if (this._deletedMessages.get(messageId) === tombstone) {
					this._deletedMessages.delete(messageId);
					for (const write of suppressed) this._chainHistoryWrite(messageId, write).catch(() => {});
				}
				throw error;
			}
			tombstone.suppressed = null;
			pending?.then(() => this._deletedMessages.get(messageId) === tombstone ? deleteHistory(items) : void 0).catch(() => {});
			this.repository.deleteMessage(messageId);
			this._notifySubscribers();
		})();
		return tombstone.deletion;
	}
	resumeRun({ stream, ...startConfig }) {
		if (!stream) throw new Error("You must pass a stream parameter to resume runs.");
		return this.startRun(startConfig, stream);
	}
	exportExternalState() {
		throw new Error("Runtime does not support exporting external states.");
	}
	import(data) {
		this._roundtripsInFlight.clear();
		this._followedDuringRun.clear();
		this._unwrittenMessages.clear();
		this._deletedMessages.clear();
		super.import(withLocalPauseReasons(data));
	}
	importExternalState() {
		throw new Error("Runtime does not support importing external states.");
	}
	unstable_notifySessionReset() {
		throw new Error("Runtime does not support resetting sessions.");
	}
	async startRun({ parentId, sourceId, runConfig }, runCallback) {
		this.ensureInitialized();
		if (this.voice) throw new Error("Cannot start a run while a voice session is connected");
		if (this._isVoiceMessage(sourceId)) throw new Error("Voice transcript messages cannot be reloaded");
		const settledWrite = this._cancelPause(parentId);
		const id = generateId();
		const message = {
			id,
			role: "assistant",
			status: { type: "running" },
			content: [],
			metadata: {
				unstable_state: this.state,
				unstable_annotations: [],
				unstable_data: [],
				steps: [],
				custom: {}
			},
			createdAt: /* @__PURE__ */ new Date()
		};
		this._unwrittenMessages.add(id);
		const run = this._runLoop(parentId, message, runConfig, runCallback);
		if (!settledWrite) return run;
		const [runResult, settledResult] = await Promise.allSettled([run, settledWrite]);
		if (runResult.status === "rejected") throw runResult.reason;
		if (settledResult.status === "rejected") throw settledResult.reason;
	}
	async _runLoop(parentId, message, runConfig, runCallback) {
		if (this.voice) throw new Error("Cannot start a run while a voice session is connected");
		this._notifyEventSubscribers("runStart", {});
		const run = {
			cancelled: false,
			resumedFromPause: message.status.type === "requires-action"
		};
		this._activeRun = run;
		this._runGeneration++;
		let active = false;
		try {
			this._queue?.notifyBusy();
			this._suggestions = [];
			this._suggestionsController?.abort();
			this._suggestionsController = null;
			this._notifySubscribers();
			do {
				message = await this.performRoundtrip(parentId, message, runConfig, run, runCallback);
				runCallback = void 0;
				if (this._activeRun !== run) break;
				let replacement = this._messageReplacements.get(message);
				while (replacement) {
					message = replacement.message;
					replacement = this._messageReplacements.get(message);
				}
				if (this.getMessageById(message.id)?.message !== message) break;
			} while (shouldContinue(message, this._options.unstable_humanToolNames) && !this.repository.hasChildren(message.id));
		} finally {
			this._notifyEventSubscribers("runEnd", {});
			active = this._activeRun === run;
			if (active) this._activeRun = null;
			if (active || run.cancelled) queueMicrotask(() => this._queue?.notifyIdle());
		}
		if (active && this.adapters.suggestion && message.status?.type !== "requires-action") {
			this._suggestionsController = new AbortController();
			const signal = this._suggestionsController.signal;
			const adapter = this.adapters.suggestion;
			(async () => {
				try {
					const promiseOrGenerator = adapter.generate({
						messages: this.messages,
						signal
					});
					await consumeSuggestionResult(promiseOrGenerator, {
						signal,
						onUpdate: (r) => {
							this._suggestions = r;
							this._notifySubscribers();
						}
					});
				} catch {}
			})();
		}
	}
	async performRoundtrip(parentId, message, runConfig, run, runCallback) {
		const modelMessages = (parentId ? this.repository.getMessages(parentId) : []).map((m) => withoutToolInteractions(m.role === "assistant" && (m.status.type === "running" || this._roundtripsInFlight.has(m.id)) ? withCancelledPause(m) : m));
		this.abortController?.abort();
		const abortController = new AbortController();
		this.abortController = abortController;
		const initialContent = message.content;
		const initialAnnotations = message.metadata?.unstable_annotations;
		const initialData = message.metadata?.unstable_data;
		const initialSteps = message.metadata?.steps;
		const initialCustom = message.metadata?.custom;
		const externalToolCallIds = /* @__PURE__ */ new Set();
		let hasStoredMessage = true;
		try {
			this.repository.getMessage(message.id);
		} catch {
			hasStoredMessage = false;
		}
		const syncOwnedMessage = () => {
			if (!hasStoredMessage) return this._activeRun === run;
			try {
				let ownedMessage = message;
				let replacement = this._messageReplacements.get(ownedMessage);
				while (replacement) {
					if (replacement.toolCallId !== void 0) externalToolCallIds.add(replacement.toolCallId);
					ownedMessage = replacement.message;
					replacement = this._messageReplacements.get(ownedMessage);
				}
				if (this.repository.getMessage(message.id).message !== ownedMessage) return false;
				message = ownedMessage;
				return true;
			} catch {
				return false;
			}
		};
		const withExternalResults = (parts) => {
			const interactions = /* @__PURE__ */ new Map();
			for (const part of message.content) if (part.type === "tool-call" && part.unstable_interactions !== void 0) interactions.set(part.toolCallId, part.unstable_interactions);
			const withInteractions = parts.map((part) => {
				if (part.type !== "tool-call" || part.unstable_interactions !== void 0) return part;
				const unstable_interactions = interactions.get(part.toolCallId);
				return unstable_interactions === void 0 ? part : {
					...part,
					unstable_interactions
				};
			});
			if (externalToolCallIds.size === 0) return withInteractions;
			const previousToolCalls = /* @__PURE__ */ new Map();
			for (const part of message.content) {
				if (part.type !== "tool-call" || !externalToolCallIds.has(part.toolCallId)) continue;
				const occurrences = previousToolCalls.get(part.toolCallId) ?? [];
				occurrences.push(part);
				previousToolCalls.set(part.toolCallId, occurrences);
			}
			const incomingOccurrences = /* @__PURE__ */ new Map();
			return withInteractions.map((part) => {
				if (part.type !== "tool-call") return part;
				const occurrence = incomingOccurrences.get(part.toolCallId) ?? 0;
				incomingOccurrences.set(part.toolCallId, occurrence + 1);
				if (part.result !== void 0 && part.isPreliminary !== true) return part;
				const completed = previousToolCalls.get(part.toolCallId)?.[occurrence];
				if (!completed || completed.result === void 0 || completed.isPreliminary === true) return part;
				const { isPreliminary: _, artifact: _artifact, modelContent: _modelContent, ...settledPart } = part;
				return {
					...settledPart,
					result: completed.result,
					isError: completed.isError,
					...completed.artifact !== void 0 && { artifact: completed.artifact },
					...completed.modelContent !== void 0 && { modelContent: completed.modelContent }
				};
			});
		};
		const updateMessage = (m) => {
			if (!syncOwnedMessage()) return;
			const newSteps = m.metadata?.steps;
			const steps = newSteps ? [...initialSteps ?? [], ...newSteps] : void 0;
			const newAnnotations = m.metadata?.unstable_annotations;
			const newData = m.metadata?.unstable_data;
			const annotations = newAnnotations ? [...initialAnnotations ?? [], ...newAnnotations] : void 0;
			const data = newData ? [...initialData ?? [], ...newData] : void 0;
			const content = m.content ? withExternalResults([...initialContent, ...m.content]) : void 0;
			message = {
				...message,
				...content ? { content } : void 0,
				status: m.status ?? message.status,
				...m.metadata ? { metadata: {
					...message.metadata,
					...m.metadata.unstable_state !== void 0 ? { unstable_state: m.metadata.unstable_state } : void 0,
					...annotations ? { unstable_annotations: annotations } : void 0,
					...data ? { unstable_data: data } : void 0,
					...steps ? { steps } : void 0,
					...m.metadata?.timing ? { timing: m.metadata.timing } : void 0,
					...m.metadata?.custom ? { custom: {
						...initialCustom ?? {},
						...m.metadata.custom
					} } : void 0
				} } : void 0
			};
			this.repository.addOrUpdateMessage(parentId, message);
			hasStoredMessage = true;
			this._notifySubscribers();
		};
		const maxSteps = this._options.maxSteps ?? 2;
		this._roundtripsInFlight.set(message.id, {
			controller: abortController,
			resumedFromPause: run.resumedFromPause
		});
		try {
			if ((message.metadata?.steps?.length ?? 0) >= maxSteps) {
				updateMessage({ status: {
					type: "incomplete",
					reason: "tool-calls"
				} });
				return message;
			}
			updateMessage({ status: { type: "running" } });
			this.repository.switchToBranch(message.id);
			this._notifySubscribers();
			this._lastRunConfig = runConfig ?? {};
			const { unstable_composerMetadata: _, ...context } = this.getModelContext();
			runCallback = runCallback ?? this.adapters.chatModel.run.bind(this.adapters.chatModel);
			const abortSignal = abortController.signal;
			const shouldCancelMessage = () => abortSignal.aborted && (message.status.type === "running" || message.status.type === "requires-action" && (this._activeRun !== run || shouldContinue(message, this._options.unstable_humanToolNames)));
			const threadId = this._getThreadId?.();
			const promiseOrGenerator = runCallback({
				messages: modelMessages,
				runConfig: this._lastRunConfig,
				abortSignal,
				context,
				unstable_assistantMessageId: message.id,
				unstable_threadId: threadId,
				unstable_parentId: parentId,
				unstable_getMessage() {
					syncOwnedMessage();
					return withoutToolInteractions(message);
				}
			});
			if (Symbol.asyncIterator in promiseOrGenerator) for await (const r of promiseOrGenerator) {
				if (abortSignal.aborted) {
					if (shouldCancelMessage()) updateMessage({ status: {
						type: "incomplete",
						reason: "cancelled"
					} });
					break;
				}
				updateMessage(r);
			}
			else updateMessage(await promiseOrGenerator);
			if (shouldCancelMessage()) updateMessage({ status: {
				type: "incomplete",
				reason: "cancelled"
			} });
			else if (message.status.type === "running") updateMessage({ status: {
				type: "complete",
				reason: "unknown"
			} });
		} catch (e) {
			if (e instanceof AbortError) updateMessage({ status: {
				type: "incomplete",
				reason: "cancelled"
			} });
			else if (e instanceof Error && e.name === "AbortError") updateMessage({ status: {
				type: "incomplete",
				reason: "cancelled"
			} });
			else {
				updateMessage({ status: {
					type: "incomplete",
					reason: "error",
					error: toAssistantError(e)
				} });
				throw e;
			}
		} finally {
			if (this.abortController === abortController) this.abortController = null;
			const holdsMessage = this._roundtripsInFlight.get(message.id)?.controller === abortController;
			if (holdsMessage) this._roundtripsInFlight.delete(message.id);
			const history = this._options.adapters.history;
			const ownsCurrentMessage = syncOwnedMessage();
			let settled = false;
			let written;
			const followedDuringRun = holdsMessage && this._followedDuringRun.delete(message.id);
			if (followedDuringRun) {
				const stored = this.getMessageById(message.id);
				if (stored?.message.role === "assistant") {
					const cancelled = withCancelledPause(stored.message);
					if (cancelled !== stored.message) {
						this.repository.addOrUpdateMessage(stored.parentId, cancelled);
						settled = true;
						if (ownsCurrentMessage) message = cancelled;
						else written = this._persistSettled(stored.parentId, cancelled);
					}
				}
			}
			if (holdsMessage && !ownsCurrentMessage && !written) {
				const stored = this.getMessageById(message.id);
				if (stored?.message.role === "assistant" && (stored.message.status.type === "complete" || stored.message.status.type === "incomplete") && this._unwrittenMessages.has(message.id)) written = this._persistSettled(stored.parentId, stored.message);
			}
			const isTerminal = message.status.type === "complete" || message.status.type === "incomplete";
			const isPausing = message.status.type === "requires-action" && !shouldContinue(message, this._options.unstable_humanToolNames);
			if (ownsCurrentMessage && (isTerminal || isPausing && history?.update)) {
				if (isTerminal && run.resumedFromPause && !followedDuringRun && !this._unwrittenMessages.has(message.id) && history && !history.update) {
					const item = {
						parentId,
						message,
						runConfig: this._lastRunConfig
					};
					written = this._chainHistoryWrite(message.id, () => this._writeHistory("append", [message.id], () => history.append(item)));
				} else written = this._persistSettled(parentId, message);
			}
			if (settled) this._notifySubscribers();
			if (written) await written;
		}
		return message;
	}
	detach() {
		invalidateThreadRuntime(this);
		this._queue = null;
		const error = new AbortError(true);
		this.abortController?.abort(error);
		this.abortController = null;
		this._suggestionsController?.abort();
		this._suggestionsController = null;
	}
	cancelRun() {
		if (this._queue) {
			if (this._options.unstable_queueClearOnCancel ?? true) this._queue.clear();
			else {
				this._queue.notifyCancelled();
				if (this._activeRun) this._activeRun.cancelled = true;
			}
		}
		const error = new AbortError(false);
		this.abortController?.abort(error);
		this.abortController = null;
		this._suggestionsController?.abort();
		this._suggestionsController = null;
	}
	_onMessageMetadataChanged(previousMessage, message) {
		this._messageReplacements.set(previousMessage, { message });
		this._persistMessageUpdate(message.id);
	}
	addToolResult({ messageId, toolCallId, result, isError, artifact, modelContent }) {
		if (this.voice) throw new Error("Cannot add a tool result while a voice session is connected");
		const messageData = this.repository.getMessage(messageId);
		const { parentId } = messageData;
		let { message } = messageData;
		if (message.role !== "assistant") throw new Error("Tried to add tool result to non-assistant message");
		let added = false;
		let found = false;
		const newContent = message.content.map((c) => {
			if (c.type !== "tool-call") return c;
			if (c.toolCallId !== toolCallId) return c;
			found = true;
			if (c.result === void 0 || c.isPreliminary === true) added = true;
			const { isPreliminary: _isPreliminary, ...part } = c;
			return {
				...part,
				result,
				isError,
				...artifact !== void 0 && { artifact },
				...modelContent !== void 0 && { modelContent }
			};
		});
		if (!found) throw new Error("Tried to add tool result to non-existing tool call");
		const previousMessage = message;
		message = {
			...message,
			content: newContent
		};
		if (previousMessage.status.type === "running") this._messageReplacements.set(previousMessage, {
			message,
			toolCallId
		});
		this.repository.addOrUpdateMessage(parentId, message);
		this._notifySubscribers();
		if (!added) return;
		if (!this._resumeIfReady(messageId)) this._persistMessageUpdate(messageId);
	}
	resumeToolCall(_options) {
		throw new Error("Local runtime does not support resuming tool calls. For human-in-the-loop tools, list the tool in unstable_humanToolNames and complete the call with addToolResult.");
	}
	async unstable_recordToolInteraction({ messageId, toolCallId, interaction }) {
		let messageData;
		try {
			messageData = this.repository.getMessage(messageId);
		} catch {
			throw new Error("Tried to record a tool interaction on a non-existing message");
		}
		const { parentId, message: previousMessage } = messageData;
		if (previousMessage.role !== "assistant") throw new Error("Tried to record a tool interaction on a non-assistant message");
		const toolCallIndex = previousMessage.content.findIndex((part) => part.type === "tool-call" && part.toolCallId === toolCallId);
		if (toolCallIndex === -1) throw new Error("Tried to record a tool interaction on a non-existing tool call");
		const target = previousMessage.content[toolCallIndex];
		if (target.type !== "tool-call") throw new Error("Tried to record a tool interaction on a non-existing tool call");
		const message = {
			...previousMessage,
			content: previousMessage.content.map((part, index) => index === toolCallIndex ? {
				...part,
				unstable_interactions: appendToolInteraction(target.unstable_interactions, interaction)
			} : part)
		};
		if (previousMessage.status.type === "running") this._messageReplacements.set(previousMessage, { message });
		this.repository.addOrUpdateMessage(parentId, message);
		this._notifySubscribers();
		this._persistMessageUpdate(message.id);
	}
	respondToToolApproval({ approvalId, approved, optionId, text, reason }) {
		if (this.voice) throw new Error("Cannot respond to a tool approval while a voice session is connected");
		let message = this.repository.getMessages().findLast((m) => m.role === "assistant" && m.content.some((c) => c.type === "tool-call" && c.approval?.id === approvalId));
		if (!message) throw new Error("Tried to respond to a non-existing tool approval");
		if (this.abortController !== null) throw new Error("Tried to respond to a tool approval while a run is in progress");
		if (message.status?.type !== "requires-action") throw new Error("Tried to respond to a tool approval on a message whose status is not requires-action");
		if (this.repository.hasChildren(message.id)) throw new Error("Tried to respond to a tool approval on a message that later messages follow");
		if (this._followedDuringRun.has(message.id)) throw new Error("Tried to respond to a tool approval that was cancelled or expired");
		const target = message.content.find((c) => c.type === "tool-call" && c.approval?.id === approvalId);
		if (target?.type !== "tool-call" || !target.approval) throw new Error("Tried to respond to a non-existing tool approval");
		if (target.approval.resolution !== void 0) throw new Error("Tried to respond to a tool approval that was cancelled or expired");
		if (target.approval.approved !== void 0) throw new Error("Tried to respond to an already decided tool approval");
		const targetApproval = target.approval;
		const newContent = message.content.map((c) => {
			if (c !== target) return c;
			const approval = {
				...targetApproval,
				approved,
				...optionId != null && { optionId },
				...text != null && { text },
				...reason != null && { reason }
			};
			if (approved) return {
				...c,
				approval
			};
			return {
				...c,
				approval,
				result: { error: reason || "Tool approval denied" },
				isError: true
			};
		});
		message = {
			...message,
			content: newContent
		};
		const { parentId } = this.repository.getMessage(message.id);
		this.repository.addOrUpdateMessage(parentId, message);
		this._notifySubscribers();
		this._notifyToolApprovalAnswered(message.id, target.toolCallId, target.toolName, approved);
		const stored = this.getMessageById(message.id);
		if (this.repository.headId === message.id && stored?.message.role === "assistant" && shouldContinue(stored.message, this._options.unstable_humanToolNames)) this._runLoop(stored.parentId, stored.message, this._lastRunConfig).catch(() => {});
		else this._persistMessageUpdate(message.id);
		return Promise.resolve();
	}
};
//#endregion
export { LocalThreadRuntimeCore };
