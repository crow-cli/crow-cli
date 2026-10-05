import { generateId } from "../../utils/id.js";
import { getThreadMessageText } from "../../utils/text.js";
import { fromThreadMessageLike } from "../../runtime/utils/thread-message-like.js";
import { FALLBACK_ID_PREFIX, bindExternalStoreMessage, getExternalStoreMessages } from "../../runtime/utils/external-store-message.js";
import { getContentAutoStatus, isAutoStatus } from "../../runtime/utils/auto-status.js";
import { ExportedMessageRepository, MessageRepository } from "../../runtime/utils/message-repository.js";
import { EMPTY_QUEUE_ITEMS } from "../../runtime/queue/queue-item.js";
import { walkToolCallTree } from "../../runtime/utils/tool-call-tree.js";
import { captureThreadRuntimeGeneration } from "../../runtime/utils/thread-runtime-lifecycle.js";
import { BaseThreadRuntimeCore } from "../../runtime/base/base-thread-runtime-core.js";
import { ThreadMessageConverter } from "./thread-message-converter.js";
import { shallowArrayEqual } from "../../runtime/utils/external-message-conversion.js";
import { ToolInvocationTracker } from "../tool-invocations/ToolInvocationTracker.js";
import { shallowEqual } from "@assistant-ui/store/client";
//#region src/runtimes/external-store/external-store-thread-runtime-core.ts
const EMPTY_ARRAY = Object.freeze([]);
const observeAdapterCallback = (name, result) => {
	Promise.resolve(result).catch((error) => {
		console.error(`[ExternalStoreThreadRuntimeCore] ${name} callback rejected`, error);
	});
};
const hasUpcomingMessage = (isRunning, messages) => {
	return isRunning && messages[messages.length - 1]?.role !== "assistant";
};
var ExternalStoreThreadRuntimeCore = class extends BaseThreadRuntimeCore {
	_capabilities = {
		switchToBranch: false,
		switchBranchDuringRun: false,
		edit: false,
		delete: false,
		reload: false,
		refetchThread: false,
		cancel: false,
		unstable_copy: false,
		speech: false,
		dictation: false,
		voice: false,
		attachments: false,
		feedback: false,
		queue: false,
		answerToolCall: false
	};
	get capabilities() {
		return this._capabilities;
	}
	_messages;
	isDisabled;
	isSendDisabled;
	get isLoading() {
		return this._store.isLoading ?? false;
	}
	get isRunning() {
		if (this._hasExecutingTools(this._store)) return true;
		return this._store.isRunning;
	}
	_getBaseMessages() {
		return this._messages;
	}
	get state() {
		return this._store.state ?? super.state;
	}
	get adapters() {
		return this._store.adapters;
	}
	get unstable_refetchThread() {
		if (!this._store.onRefetchThread) return void 0;
		return () => this._store.onRefetchThread();
	}
	suggestions = [];
	extras = void 0;
	_converter = new ThreadMessageConverter();
	_pendingDeleteEvictions = /* @__PURE__ */ new Map();
	_optimistic = null;
	_store;
	_getInitializePromise;
	__internal_setGetInitializePromise(getPromise) {
		this._getInitializePromise = getPromise;
	}
	_transformedQueue;
	/**
	* Client-side tool-invocations pipeline. Constructed lazily on first
	* snapshot — only when `adapter.unstable_enableToolInvocations === true`.
	*/
	_toolInvocations = null;
	_toolStatuses = /* @__PURE__ */ new Map();
	_effectiveIsRunning = false;
	_inTrackerUpdate = false;
	_pendingRunningRefresh = false;
	/**
	* Tracker mutations initiated by this class (setState, reset) can publish
	* status changes synchronously. Re-entering the snapshot pipeline from
	* inside them would feed the tracker a stale snapshot and consume the
	* restore arming a reset just installed, so the running refresh is
	* deferred until the mutation returns and stays off the tracker.
	*/
	_runTrackerUpdate(fn) {
		this._inTrackerUpdate = true;
		try {
			fn();
		} finally {
			this._inTrackerUpdate = false;
		}
		if (this._pendingRunningRefresh) {
			this._pendingRunningRefresh = false;
			this._refreshEffectiveIsRunning();
		}
	}
	_refreshEffectiveIsRunning() {
		const isRunning = this._getEffectiveIsRunning(this._store);
		if (this._effectiveIsRunning === isRunning) return;
		this._effectiveIsRunning = isRunning;
		this._notifyEventSubscribers(isRunning ? "runStart" : "runEnd", {});
		this._notifySubscribers();
	}
	_hasExecutingTools(store) {
		if (store.unstable_enableToolInvocations !== true) return false;
		if (this._toolInvocations === null) return false;
		for (const status of this._toolStatuses.values()) if (status.type === "executing") return true;
		return false;
	}
	_getEffectiveIsRunning(store) {
		return (store.isRunning ?? false) || this._hasExecutingTools(store);
	}
	beginEdit(messageId) {
		if (!this._store.onEdit) throw new Error("Runtime does not support editing.");
		super.beginEdit(messageId);
	}
	constructor(contextProvider, store) {
		super(contextProvider);
		this.__internal_setAdapter(store);
	}
	__internal_setAdapter(store) {
		if (this._store === store) return;
		this._updateStoreSnapshot(store);
	}
	_updateStoreSnapshot(store) {
		const previousIsRunning = this._effectiveIsRunning;
		this.isDisabled = store.isDisabled ?? false;
		this.isSendDisabled = store.isSendDisabled ?? false;
		const oldStore = this._store;
		this._store = store;
		const isRunning = this._getEffectiveIsRunning(store);
		const repositoryInstance = store.unstable_messageRepositoryInstance;
		const repositoryChanged = repositoryInstance !== void 0 && repositoryInstance !== this.repository;
		if (repositoryChanged) {
			this.repository = repositoryInstance;
			this._pendingDeleteEvictions.clear();
			const head = this.repository.getMessages();
			const tail = head.at(-1);
			this._optimistic = tail?.metadata.isOptimistic ? {
				id: tail.id,
				parentId: head.at(-2)?.id ?? null
			} : null;
		}
		if (oldStore?.queue !== store.queue) {
			this._transformedQueue = void 0;
			store.queue?.__internal_setDispatchTransform?.((message) => {
				const parentId = this.messages.at(-1)?.id ?? null;
				return this.enrichAppendMetadata({
					...message,
					parentId
				}, parentId);
			});
			if (store.queue?.__internal_setDispatchTransform) this._transformedQueue = store.queue;
		}
		if (this.extras !== store.extras) this.extras = store.extras;
		const newSuggestions = store.suggestions ?? EMPTY_ARRAY;
		if (!shallowEqual(this.suggestions, newSuggestions)) this.suggestions = newSuggestions;
		const newCapabilities = {
			switchToBranch: this._store.setMessages !== void 0,
			switchBranchDuringRun: false,
			edit: this._store.onEdit !== void 0,
			delete: this._store.onDelete !== void 0 || this._store.setMessages !== void 0,
			reload: this._store.onReload !== void 0,
			refetchThread: this._store.onRefetchThread !== void 0,
			cancel: this._store.onCancel !== void 0,
			speech: this._store.adapters?.speech !== void 0,
			dictation: this._store.adapters?.dictation !== void 0,
			voice: this._store.adapters?.voice !== void 0,
			unstable_copy: this._store.unstable_capabilities?.copy !== false,
			attachments: !!this._store.adapters?.attachments,
			feedback: !!this._store.adapters?.feedback,
			queue: this._store.queue !== void 0,
			answerToolCall: this._store.onAddToolResult !== void 0 || this._store.onResumeToolCall !== void 0 || this._store.onRespondToToolApproval !== void 0 || this._store.unstable_enableToolInvocations === true
		};
		if (!shallowEqual(this._capabilities, newCapabilities)) this._capabilities = newCapabilities;
		let messages;
		if (store.messageRepository) {
			if (oldStore && !repositoryChanged && oldStore.isRunning === store.isRunning && oldStore.messageRepository === store.messageRepository && previousIsRunning === isRunning) {
				this._notifySubscribers();
				return;
			}
			const incoming = store.messageRepository.messages;
			const headId = store.messageRepository.headId ?? incoming.at(-1)?.message.id ?? null;
			if (oldStore && !repositoryChanged && oldStore.messageRepository === store.messageRepository) {
				this.repository.resetHead(headId);
				messages = this.repository.getMessages();
			} else {
				const incomingIds = new Set(incoming.map(({ message }) => message.id));
				for (const { message, parentId } of incoming) this.repository.addOrUpdateMessage(parentId, message);
				for (const { message } of this.repository.export().messages) if (!incomingIds.has(message.id)) this.repository.deleteMessage(message.id);
				this._pendingDeleteEvictions.clear();
				this.repository.resetHead(headId);
				messages = this.repository.getMessages();
			}
		} else if (store.messages) {
			if (oldStore) {
				if (oldStore.convertMessage !== store.convertMessage) this._converter = new ThreadMessageConverter();
				else if (!repositoryChanged && oldStore.isRunning === store.isRunning && oldStore.messages === store.messages && previousIsRunning === isRunning) {
					this._notifySubscribers();
					return;
				}
			}
			messages = !store.convertMessage ? store.messages : this._converter.convertMessages(store.messages, (cache, m, idx) => {
				if (!store.convertMessage) return m;
				const isLast = idx === (store.messages?.length ?? 0) - 1;
				const fallbackId = `${FALLBACK_ID_PREFIX}${idx}`;
				if (cache && (cache.role !== "assistant" || !isAutoStatus(cache.status) || cache.status === getContentAutoStatus(cache.content, isLast, isRunning))) {
					if (cache.id.startsWith("__external_store_fallback_") && cache.id !== fallbackId) {
						const updated = {
							...cache,
							id: fallbackId
						};
						bindExternalStoreMessage(updated, m);
						return updated;
					}
					return cache;
				}
				const messageLike = store.convertMessage(m, idx);
				const newMessage = fromThreadMessageLike(messageLike, fallbackId, getContentAutoStatus(messageLike.content, isLast, isRunning));
				bindExternalStoreMessage(newMessage, m);
				return newMessage;
			});
			const seenIds = /* @__PURE__ */ new Set();
			const deduped = [];
			for (let i = messages.length - 1; i >= 0; i--) {
				const message = messages[i];
				if (seenIds.has(message.id)) {
					console.warn(`ExternalStoreThreadRuntimeCore: duplicate message id "${message.id}" in the provided messages array; keeping the last occurrence.`);
					continue;
				}
				seenIds.add(message.id);
				deduped.push(message);
			}
			if (deduped.length !== messages.length) messages = deduped.reverse();
			for (let i = 0; i < messages.length; i++) {
				const message = messages[i];
				const parent = messages[i - 1];
				this.repository.addOrUpdateMessage(parent?.id ?? null, message);
			}
			if (this._pendingDeleteEvictions.size > 0) {
				const incomingIds = new Set(messages.map((m) => m.id));
				for (const [id, calls] of this._pendingDeleteEvictions) {
					if (incomingIds.has(id)) {
						if (calls.size === 0) this._pendingDeleteEvictions.delete(id);
						continue;
					}
					this._pendingDeleteEvictions.delete(id);
					try {
						this.repository.getMessage(id);
					} catch {
						continue;
					}
					this.repository.deleteMessage(id);
				}
			}
		} else throw new Error("ExternalStoreAdapter must provide either 'messages' or 'messageRepository'");
		if (messages.length > 0) this.ensureInitialized();
		this._effectiveIsRunning = isRunning;
		if (previousIsRunning !== isRunning) {
			if (isRunning) this._notifyEventSubscribers("runStart", {});
			else this._notifyEventSubscribers("runEnd", {});
		}
		let optimisticId = null;
		if (hasUpcomingMessage(isRunning, messages)) {
			const parentId = messages.at(-1)?.id ?? null;
			if (this._optimistic?.parentId !== parentId) this._optimistic = {
				id: generateId(),
				parentId
			};
			optimisticId = this._optimistic.id;
			this.repository.addOrUpdateMessage(parentId, fromThreadMessageLike({
				role: "assistant",
				content: [],
				metadata: { isOptimistic: true }
			}, optimisticId, { type: "running" }));
		}
		if (optimisticId === null) this._optimistic = null;
		this.repository.resetHead(optimisticId ?? messages.at(-1)?.id ?? null);
		const messagesSnapshot = this.repository.getMessages();
		if (!this._messages || !shallowArrayEqual(this._messages, messagesSnapshot)) this._messages = messagesSnapshot;
		if (this._voiceMessages.length > 0) {
			const hostIds = new Set(this._messages.map((message) => message.id));
			const remaining = this._voiceMessages.filter((message) => !hostIds.has(message.id));
			if (remaining.length !== this._voiceMessages.length) {
				this._voiceMessages = remaining;
				this._markVoiceMessagesDirty();
			}
		}
		if (repositoryChanged) this._runTrackerUpdate(() => this._toolInvocations?.reset());
		this._runTrackerUpdate(() => this._driveToolInvocations());
		this._notifySubscribers();
	}
	/**
	* Feed the current message snapshot into the tool-invocations tracker.
	* Opt-in via `adapter.unstable_enableToolInvocations: true`. The tracker
	* itself is fail-silent — see ToolInvocationTracker for the
	* state-transition contract.
	*/
	_driveToolInvocations() {
		if (!this._store.unstable_enableToolInvocations) {
			if (this._toolInvocations) {
				this._toolInvocations.reset();
				this._toolInvocations = null;
				this._toolStatuses = /* @__PURE__ */ new Map();
				this._store.setToolStatuses?.({});
			}
			return;
		}
		if (!this._toolInvocations) this._toolInvocations = new ToolInvocationTracker(() => this.getModelContext().tools, {
			onResult: (command) => {
				try {
					const messageId = this._findMessageIdForToolCall(command.toolCallId);
					if (messageId === void 0) return;
					observeAdapterCallback("onAddToolResult", this._store.onAddToolResult?.({
						messageId,
						toolCallId: command.toolCallId,
						toolName: command.toolName,
						result: command.result,
						isError: command.isError,
						...command.artifact !== void 0 && { artifact: command.artifact },
						...command.modelContent !== void 0 && { modelContent: command.modelContent }
					}));
				} catch (err) {
					console.error("[ExternalStoreThreadRuntimeCore] onAddToolResult dispatch failed", err);
				}
			},
			onStatusesChange: (statuses) => {
				const hadExecutingTools = this._hasExecutingTools(this._store);
				this._toolStatuses = statuses;
				try {
					this._store.setToolStatuses?.(Object.fromEntries(statuses));
				} finally {
					if (hadExecutingTools !== this._hasExecutingTools(this._store)) {
						if (this._inTrackerUpdate) this._pendingRunningRefresh = true;
						else this._updateStoreSnapshot(this._store);
					}
				}
			}
		}, (toolCall) => this._store.unstable_isClientToolCall?.(toolCall));
		this._toolInvocations.setState({
			messages: this._messages,
			isRunning: this._getEffectiveIsRunning(this._store),
			...this._store.isLoading !== void 0 && { isLoading: this._store.isLoading }
		});
	}
	/**
	* Lookup table from `toolCallId` to the owning assistant message's `id`,
	* rebuilt lazily when `_messages` changes (see `_messagesForToolCallIndex`).
	*/
	_toolCallToMessageId = /* @__PURE__ */ new Map();
	_messagesForToolCallIndex = null;
	/**
	* Look up the assistant message that owns a tool-call part. Lazily builds
	* (and caches) a `toolCallId → messageId` map keyed off the current
	* `_messages` reference, so onResult dispatches stay O(1) instead of
	* walking the full thread on every result.
	*/
	_findMessageIdForToolCall(toolCallId) {
		if (this._messagesForToolCallIndex !== this._messages) {
			this._toolCallToMessageId.clear();
			for (const { part, messageId } of walkToolCallTree(this._messages)) this._toolCallToMessageId.set(part.toolCallId, messageId);
			this._messagesForToolCallIndex = this._messages;
		}
		return this._toolCallToMessageId.get(toolCallId);
	}
	switchToBranch(branchId) {
		if (!this._store.setMessages) throw new Error("Runtime does not support switching branches.");
		if (this._getEffectiveIsRunning(this._store)) return;
		const onBranchChange = this._store.unstable_onBranchChange;
		const previousHeadId = onBranchChange ? this.repository.canonicalHeadId : null;
		this.repository.switchToBranch(branchId);
		this._pendingDeleteEvictions.clear();
		this.updateMessages(this.repository.getMessages());
		if (onBranchChange) this._notifyBranchChange(previousHeadId, onBranchChange);
	}
	/**
	* Emit `unstable_onBranchChange` for an explicit branch switch. Reads the
	* canonical head from the repository (which skips optimistic/transient
	* messages) and de-dupes switches that leave the canonical head unchanged.
	* Comparing against the head observed just before the switch — rather than the
	* last emitted head — keeps a switch firing after an adapter resync moved the
	* head elsewhere in the meantime.
	*/
	_notifyBranchChange(previousHeadId, onBranchChange) {
		const headId = this.repository.canonicalHeadId;
		if (headId === previousHeadId) return;
		onBranchChange({
			headId,
			visibleMessageIds: this.repository.getMessages().map((m) => m.id)
		});
	}
	async append(rawMessage) {
		let message = {
			...rawMessage,
			parentId: this._resolveAppendParent(rawMessage.parentId)
		};
		if (this.voice) return this._appendToVoiceSession(message);
		if (this._isVoiceMessage(message.sourceId)) throw new Error("Voice transcript messages cannot be edited");
		const isEdit = message.sourceId != null || message.parentId !== (this._getBaseMessages().at(-1)?.id ?? null);
		message = !isEdit && this._store.queue && this._store.queue === this._transformedQueue ? message : this.enrichAppendMetadata(message);
		const generation = captureThreadRuntimeGeneration(this);
		this.ensureInitialized();
		const initPromise = this._getInitializePromise?.();
		if (!isEdit && this._store.queue) {
			if (initPromise) await initPromise;
			if (generation.aborted) return;
			if (message.steer === true && this._store.queue.sendNow) this._store.queue.sendNow(message);
			else if (message.steer ?? this._getEffectiveIsRunning(this._store)) this._store.queue.steer(message);
			else this._store.queue.enqueue(message);
			return;
		}
		initPromise?.catch(() => {});
		if (message.startRun ?? message.role === "user") await this._toolInvocations?.abort({ discardPending: true });
		if (generation.aborted) return;
		if (isEdit) {
			if (!this._store.onEdit) throw new Error("Runtime does not support editing messages.");
			this._pendingDeleteEvictions.clear();
			await this._store.onEdit(message);
		} else await this._store.onNew(message);
	}
	_commitVoiceMessage(message) {
		const generation = captureThreadRuntimeGeneration(this);
		if (generation.aborted) {
			this._dropVoiceMessage(message.id, false);
			return;
		}
		const barrier = this._getVoiceCommitBarrier();
		if (!barrier) {
			this._store.onVoiceTranscript?.(message);
			return;
		}
		const repository = this.repository;
		return barrier.then(() => {
			if (generation.aborted || this.repository !== repository) {
				this._dropVoiceMessage(message.id, true);
				return;
			}
			this._store.onVoiceTranscript?.(message);
		});
	}
	async deleteMessage(messageId) {
		if (this._store.onDelete) {
			const wasVisible = this.repository.getMessages().some((m) => m.id === messageId);
			const call = Symbol();
			if (wasVisible) {
				const calls = this._pendingDeleteEvictions.get(messageId) ?? /* @__PURE__ */ new Set();
				this._pendingDeleteEvictions.set(messageId, calls.add(call));
			}
			try {
				await this._store.onDelete(messageId);
			} finally {
				this._pendingDeleteEvictions.get(messageId)?.delete(call);
			}
			return;
		}
		if (!this._store.setMessages) throw new Error("Runtime does not support deleting messages.");
		if (this._getEffectiveIsRunning(this._store)) await this._toolInvocations?.abort();
		const messages = this.repository.getMessages();
		if (messages.findIndex((m) => m.id === messageId) === -1) throw new Error("Message not found.");
		this._pendingDeleteEvictions.clear();
		this.updateMessages(messages.filter((message) => message.id !== messageId));
		this._evictDeletedMessage(messageId);
	}
	_evictDeletedMessage(messageId) {
		if (messageId.startsWith("__external_store_fallback_")) return;
		try {
			this.repository.getMessage(messageId);
		} catch {
			return;
		}
		this.repository.deleteMessage(messageId);
		this._publishRepositoryMessages();
	}
	_publishRepositoryMessages() {
		const messages = this.repository.getMessages();
		if (!shallowArrayEqual(this._messages, messages)) this._messages = messages;
		this._notifySubscribers();
	}
	getQueueItems() {
		return this._store?.queue?.items ?? EMPTY_QUEUE_ITEMS;
	}
	getSteerQueueItems() {
		return this._store?.queue?.steerItems ?? EMPTY_QUEUE_ITEMS;
	}
	moveQueueItem(queueItemId, placement) {
		this._store?.queue?.move(queueItemId, placement);
	}
	editQueueItem(queueItemId, message) {
		this._store?.queue?.edit(queueItemId, message);
	}
	removeQueueItem(queueItemId) {
		this._store?.queue?.remove(queueItemId);
	}
	async startRun(config) {
		if (!this._store.onReload) throw new Error("Runtime does not support reloading messages.");
		if (this.voice) throw new Error("Cannot start a run while a voice session is connected");
		if (this._isVoiceMessage(config.sourceId)) throw new Error("Voice transcript messages cannot be reloaded");
		const visible = this.repository.getMessages();
		const kept = new Set(visible.slice(0, visible.findIndex((m) => m.id === config.parentId) + 1).map((m) => m.id));
		for (const id of this._pendingDeleteEvictions.keys()) if (!kept.has(id)) this._pendingDeleteEvictions.delete(id);
		await this._toolInvocations?.abort({ discardPending: true });
		await this._store.onReload(config.parentId, config);
	}
	async resumeRun(config) {
		if (!this._store.onResume) throw new Error("Runtime does not support resuming runs.");
		if (this.voice) throw new Error("Cannot start a run while a voice session is connected");
		if (this._isVoiceMessage(config.sourceId)) throw new Error("Voice transcript messages cannot be reloaded");
		await this._store.onResume(config);
	}
	exportExternalState() {
		if (!this._store.onExportExternalState) throw new Error("Runtime does not support exporting external states.");
		return this._store.onExportExternalState();
	}
	importExternalState(state) {
		if (!this._store.onLoadExternalState) throw new Error("Runtime does not support importing external states.");
		this._runTrackerUpdate(() => this._toolInvocations?.reset());
		this._store.onLoadExternalState(state);
	}
	/**
	* Adapter-facing notification that the backing session was discarded.
	* Clears session-scoped tool-invocation state and parks queued work,
	* without run-cancel semantics (`onCancel`, composer draft restoration).
	*/
	unstable_notifySessionReset() {
		this._runTrackerUpdate(() => this._toolInvocations?.reset());
		this._store.queue?.__internal_notifyCancelled?.();
	}
	cancelRun() {
		if (!this._store.onCancel) throw new Error("Runtime does not support cancelling runs.");
		const generation = captureThreadRuntimeGeneration(this);
		this._toolInvocations?.abort({ discardPending: true });
		this._store.queue?.__internal_notifyCancelled?.();
		observeAdapterCallback("onCancel", this._store.onCancel());
		this.dropEmptyOptimisticHead();
		const messages = this.repository.getMessages();
		const previousMessage = messages[messages.length - 1];
		const trailingUserLeaf = this._store.setMessages !== void 0 && previousMessage?.role === "user" && previousMessage.id === messages.at(-1)?.id && previousMessage.content.every((part) => part.type === "text") ? previousMessage : void 0;
		let movedLeaf;
		if (trailingUserLeaf) {
			const draft = {
				text: getThreadMessageText(trailingUserLeaf),
				attachments: trailingUserLeaf.attachments,
				quote: trailingUserLeaf.metadata.custom.quote
			};
			if (this.composer.restoreDraft(draft)) {
				this.repository.deleteMessage(trailingUserLeaf.id);
				movedLeaf = {
					id: trailingUserLeaf.id,
					draft
				};
			}
		}
		this._publishRepositoryMessages();
		setTimeout(() => {
			if (generation.aborted) return;
			this.dropEmptyOptimisticHead();
			if (movedLeaf) {
				const current = this.repository.getMessages();
				if (current.at(-1)?.id === movedLeaf.id) this.repository.deleteMessage(movedLeaf.id);
				else if (current.some((m) => m.id === movedLeaf.id)) this.composer.retractDraft(movedLeaf.draft);
			}
			this._publishRepositoryMessages();
			this.updateMessages(this._messages);
		}, 0);
	}
	dropEmptyOptimisticHead() {
		const head = this.repository.getMessages().at(-1);
		if (head && head.metadata.isOptimistic && head.content.length === 0) this.repository.deleteMessage(head.id);
	}
	addToolResult(options) {
		if (!this._store.onAddToolResult) throw new Error("Runtime does not support tool results.");
		observeAdapterCallback("onAddToolResult", this._store.onAddToolResult(options));
	}
	resumeToolCall(options) {
		if (this._toolInvocations?.resume(options.toolCallId, options.payload) ?? false) return;
		if (this._store.onResumeToolCall) {
			this._store.onResumeToolCall(options);
			return;
		}
		throw new Error(`Tool call ${options.toolCallId} is not waiting for resume.`);
	}
	respondToToolApproval(options) {
		if (!this._store.onRespondToToolApproval) throw new Error("Runtime does not support tool approvals.");
		const message = this.messages.findLast((candidate) => candidate.role === "assistant" && candidate.content.some((part) => part.type === "tool-call" && part.approval?.id === options.approvalId));
		const toolCall = message?.content.find((part) => part.type === "tool-call" && part.approval?.id === options.approvalId);
		try {
			return Promise.resolve(this._store.onRespondToToolApproval(options)).then(() => {
				if (message && toolCall?.type === "tool-call") this._notifyToolApprovalAnswered(message.id, toolCall.toolCallId, toolCall.toolName, options.approved);
			});
		} catch (error) {
			return Promise.reject(error);
		}
	}
	async unstable_recordToolInteraction(options) {
		if (!this._store.unstable_onRecordToolInteraction) throw new Error("Runtime does not support recording tool interactions.");
		await this._store.unstable_onRecordToolInteraction(options);
	}
	reset(initialMessages) {
		const repo = new MessageRepository();
		repo.import(ExportedMessageRepository.fromArray(initialMessages ?? []));
		this.updateMessages(repo.getMessages());
	}
	import(data) {
		super.import(data);
		if (this._store.onImport) this._store.onImport(this.repository.getMessages());
	}
	updateMessages = (messages) => {
		if (this._store.convertMessage !== void 0) this._store.setMessages?.(messages.flatMap(getExternalStoreMessages));
		else this._store.setMessages?.(messages);
	};
};
//#endregion
export { ExternalStoreThreadRuntimeCore, hasUpcomingMessage };
