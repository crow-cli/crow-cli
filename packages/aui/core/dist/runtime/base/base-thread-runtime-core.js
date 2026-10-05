import { generateId } from "../../utils/id.js";
import { notifyEventListeners } from "../../utils/notify-event-listeners.js";
import { getThreadMessageText } from "../../utils/text.js";
import { gateInteractableComposerMetadata } from "../../model-context/interactable-composer-metadata.js";
import { BaseSubscribable, notifySubscribers } from "../../subscribable/subscribable.js";
import { MessageNotSentError } from "../../types/error.js";
import { ExportedMessageRepository, MessageRepository } from "../utils/message-repository.js";
import { captureThreadRuntimeDisposal, captureThreadRuntimeGeneration } from "../utils/thread-runtime-lifecycle.js";
import { DefaultThreadComposerRuntimeCore } from "./default-thread-composer-runtime-core.js";
import { DefaultEditComposerRuntimeCore } from "./default-edit-composer-runtime-core.js";
//#region src/runtime/base/base-thread-runtime-core.ts
var BaseThreadRuntimeCore = class extends BaseSubscribable {
	_isInitialized = false;
	repository = new MessageRepository();
	_voiceMessages = [];
	_voiceGeneration = 0;
	_cachedMergedMessages = null;
	_cachedVoiceGeneration = -1;
	_cachedMergedBase = null;
	_markVoiceMessagesDirty() {
		this._voiceGeneration++;
		this._cachedMergedMessages = null;
	}
	_getBaseMessages() {
		return this.repository.getMessages();
	}
	_commitVoiceMessage(_message) {}
	_onMessageMetadataChanged(_previousMessage, _message) {}
	_dropVoiceMessage(messageId, notify) {
		const index = this._voiceMessages.findIndex((voiceMessage) => voiceMessage.id === messageId);
		if (index === -1) return;
		this._voiceMessages.splice(index, 1);
		this._markVoiceMessagesDirty();
		if (notify) this._notifySubscribers();
	}
	get messages() {
		if (this._voiceMessages.length === 0) return this._getBaseMessages();
		const base = this._getBaseMessages();
		if (this._cachedVoiceGeneration !== this._voiceGeneration || this._cachedMergedBase !== base) {
			const baseMessageIds = new Set(base.map((message) => message.id));
			this._cachedMergedMessages = [...base, ...this._voiceMessages.filter((message) => !baseMessageIds.has(message.id))];
			this._cachedVoiceGeneration = this._voiceGeneration;
			this._cachedMergedBase = base;
		}
		return this._cachedMergedMessages;
	}
	get state() {
		let mostRecentAssistantMessage;
		for (const message of this.messages) if (message.role === "assistant") mostRecentAssistantMessage = message;
		return mostRecentAssistantMessage?.metadata.unstable_state ?? null;
	}
	composer = new DefaultThreadComposerRuntimeCore(this);
	_contextProvider;
	constructor(_contextProvider) {
		super();
		this._contextProvider = _contextProvider;
		captureThreadRuntimeDisposal(this).addEventListener("abort", () => {
			this.composer.__internal_dispose();
			for (const composer of this._editComposers.values()) composer.__internal_dispose();
		});
	}
	getModelContext() {
		return this._contextProvider.getModelContext();
	}
	/**
	* Stamps provider-contributed composer metadata onto an outgoing message.
	* Called at dispatch rather than in the composer, so programmatic sends are
	* covered too, and exactly once per message: a queued send is stamped when
	* it leaves the lane, never when it enters.
	*
	* Only user messages are stamped, matching the readers: both the version
	* fold and the model injection skip every other role.
	*
	* @param anchorId Message the gated branch prefix ends at. A queued send
	* passes the current tail, having waited through a run that grew the prefix
	* past the parent it was created with.
	*/
	enrichAppendMetadata(message, anchorId = message.parentId) {
		if (message.role !== "user") return message;
		const messages = this.messages;
		const parentIndex = anchorId === null ? -1 : messages.findIndex((m) => m.id === anchorId);
		const composerMetadata = gateInteractableComposerMetadata(this.getModelContext().unstable_composerMetadata, messages.slice(0, parentIndex + 1));
		if (!composerMetadata) return message;
		return {
			...message,
			metadata: {
				...message.metadata,
				custom: {
					...message.metadata?.custom,
					...composerMetadata
				}
			}
		};
	}
	_editComposers = /* @__PURE__ */ new Map();
	getEditComposer(messageId) {
		return this._editComposers.get(messageId);
	}
	_isVoiceMessage(messageId) {
		return messageId !== null && this._voiceMessages.some((m) => m.id === messageId);
	}
	_resolveAppendParent(parentId) {
		return this._isVoiceMessage(parentId) ? this._getBaseMessages().at(-1)?.id ?? null : parentId;
	}
	beginEdit(messageId) {
		if (this.voice) throw new Error("Cannot edit a message while a voice session is connected");
		if (this._isVoiceMessage(messageId)) throw new Error("Voice transcript messages cannot be edited");
		if (this._editComposers.has(messageId)) throw new Error("Edit already in progress");
		this._editComposers.set(messageId, new DefaultEditComposerRuntimeCore(this, () => this._editComposers.delete(messageId), this.repository.getMessage(messageId)));
		this._notifySubscribers();
	}
	getMessageById(messageId) {
		try {
			return this.repository.getMessage(messageId);
		} catch {
			const baseMessages = this.repository.getMessages();
			const voiceIdx = this._voiceMessages.findIndex((m) => m.id === messageId);
			if (voiceIdx !== -1) return {
				parentId: voiceIdx > 0 ? this._voiceMessages[voiceIdx - 1].id : baseMessages.at(-1)?.id ?? null,
				message: this._voiceMessages[voiceIdx],
				index: baseMessages.length + voiceIdx
			};
			return;
		}
	}
	getBranches(messageId) {
		if (this._voiceMessages.some((m) => m.id === messageId)) return [];
		return this.repository.getBranches(messageId);
	}
	switchToBranch(branchId) {
		this.repository.switchToBranch(branchId);
		this._notifySubscribers();
	}
	_notifyEventSubscribers(event, payload) {
		const subscribers = this._eventSubscribers.get(event);
		if (!subscribers) return;
		notifyEventListeners(subscribers, payload, `Thread runtime "${event}"`);
	}
	_notifyToolApprovalAnswered(messageId, toolCallId, toolName, approved) {
		this._notifyEventSubscribers("toolApprovalAnswered", {
			messageId,
			toolCallId,
			toolName,
			approved
		});
	}
	submitFeedback({ messageId, type, comment }) {
		const adapter = this.adapters?.feedback;
		const entry = this.getMessageById(messageId);
		if (!entry) throw new Error(`Message not found: ${messageId}`);
		const { message, parentId } = entry;
		const trimmed = comment?.trim();
		const feedback = {
			type,
			...trimmed ? { comment: trimmed } : void 0
		};
		adapter?.submit({
			message,
			...feedback
		});
		if (message.role === "assistant") {
			const updatedMessage = {
				...message,
				metadata: {
					...message.metadata,
					submittedFeedback: feedback
				}
			};
			const voiceIdx = this._voiceMessages.findIndex((voiceMessage) => voiceMessage.id === messageId);
			if (voiceIdx === -1) {
				this.repository.addOrUpdateMessage(parentId, updatedMessage);
				this._onMessageMetadataChanged(message, updatedMessage);
			} else {
				this._voiceMessages[voiceIdx] = updatedMessage;
				if (this._currentAssistantMsg === message) this._currentAssistantMsg = updatedMessage;
				this._markVoiceMessagesDirty();
			}
		}
		this._notifySubscribers();
	}
	_stopSpeaking;
	speech;
	speak(messageId) {
		const adapter = this.adapters?.speech;
		if (!adapter) throw new Error("Speech adapter not configured");
		const entry = this.getMessageById(messageId);
		if (!entry) throw new Error(`Message not found: ${messageId}`);
		const { message } = entry;
		const previousStop = this._stopSpeaking;
		let utterance;
		try {
			previousStop?.();
			utterance = adapter.speak(getThreadMessageText(message));
		} catch (error) {
			if (previousStop && !this._stopSpeaking) try {
				this._notifySubscribers();
			} catch (notificationError) {
				console.error("[assistant-ui] Speech rollback notification threw", notificationError);
			}
			throw error;
		}
		let unsub;
		const clear = () => {
			this._stopSpeaking = void 0;
			this.speech = void 0;
			const cleanup = unsub;
			unsub = void 0;
			cleanup?.();
		};
		const stop = () => {
			if (this._stopSpeaking !== stop) return;
			try {
				clear();
			} finally {
				utterance.cancel();
			}
		};
		const update = () => {
			if (this._stopSpeaking !== stop) return;
			if (utterance.status.type === "ended") notifySubscribers([clear, () => this._notifySubscribers()]);
			else {
				this.speech = {
					messageId,
					status: utterance.status
				};
				this._notifySubscribers();
			}
		};
		this._stopSpeaking = stop;
		try {
			unsub = utterance.subscribe(update);
			if (this._stopSpeaking !== stop) {
				unsub();
				return;
			}
			update();
		} catch (error) {
			if (this._stopSpeaking === stop) try {
				notifySubscribers([stop, () => this._notifySubscribers()]);
			} catch (cleanupError) {
				console.error("[assistant-ui] Speech rollback cleanup threw", cleanupError);
			}
			throw error;
		}
	}
	stopSpeaking() {
		if (!this._stopSpeaking) throw new Error("No message is being spoken");
		notifySubscribers([this._stopSpeaking, () => this._notifySubscribers()]);
	}
	_voiceSession;
	_voiceUnsubs = [];
	voice;
	_voiceVolume = 0;
	_voiceVolumeSubscribers = /* @__PURE__ */ new Set();
	getVoiceVolume = () => this._voiceVolume;
	subscribeVoiceVolume = (callback) => {
		this._voiceVolumeSubscribers.add(callback);
		return () => this._voiceVolumeSubscribers.delete(callback);
	};
	_onVoiceConnected() {}
	_onVoiceDisconnected() {}
	_toVoiceSessionState(session, status, mode) {
		return {
			status,
			isMuted: session.isMuted,
			mode,
			canSendText: status.type === "running" && session.sendText !== void 0
		};
	}
	_isRunActive() {
		if (this.isRunning) return true;
		const last = this._getBaseMessages().at(-1);
		return last?.role === "assistant" && (last.status.type === "running" || last.status.type === "requires-action");
	}
	/**
	* Waits for a pending history import before a voice message is committed.
	* The import may begin before or after the voice session connects, so the
	* loading state must be rechecked when the commit is ready to run. The wait
	* also ends when the runtime is invalidated, since a superseded runtime may
	* never learn that loading ended.
	*/
	_getVoiceCommitBarrier() {
		if (!this.isLoading) return void 0;
		const generation = captureThreadRuntimeGeneration(this);
		return (async () => {
			while (this.isLoading && !generation.aborted) await new Promise((resolve) => {
				const wake = () => {
					unsubscribe();
					generation.removeEventListener("abort", wake);
					resolve();
				};
				const unsubscribe = this.subscribe(wake);
				generation.addEventListener("abort", wake);
			});
		})();
	}
	connectVoice() {
		const adapter = this.adapters?.voice;
		if (!adapter) throw new Error("Voice adapter not configured");
		if (this._isRunActive()) throw new Error("Cannot start a voice session while a run is in progress or paused on a pending tool action");
		const replacing = this._voiceSession !== void 0;
		try {
			this._disconnectVoice(false);
		} catch (error) {
			console.error("[assistant-ui] Voice cleanup threw before reconnect", error);
		}
		let session;
		try {
			session = adapter.connect({});
		} catch (error) {
			if (replacing && this._voiceSession === void 0) this._onVoiceDisconnected();
			throw error;
		}
		this._voiceSession = session;
		const unsubs = [];
		this._voiceUnsubs = unsubs;
		const finishDetachedSetup = () => {
			if (this._voiceSession === session && this._voiceUnsubs === unsubs) return false;
			try {
				notifySubscribers(unsubs.splice(0));
			} catch (error) {
				console.error("[assistant-ui] Detached voice setup cleanup threw", error);
			}
			return true;
		};
		try {
			let currentMode = "listening";
			this.voice = this._toVoiceSessionState(session, session.status, currentMode);
			this._voiceVolume = 0;
			this._notifySubscribers();
			if (finishDetachedSetup()) return;
			unsubs.push(session.onStatusChange((status) => {
				if (this._voiceSession !== session) return;
				if (status.type === "ended") {
					this._finishVoiceAssistantMessage();
					this._voiceSession = void 0;
					this.voice = void 0;
					this._onVoiceDisconnected();
				} else this.voice = this._toVoiceSessionState(session, status, currentMode);
				this._notifySubscribers();
			}));
			if (finishDetachedSetup()) return;
			unsubs.push(session.onModeChange((mode) => {
				if (this._voiceSession !== session) return;
				currentMode = mode;
				if (this.voice) {
					this.voice = {
						...this.voice,
						mode
					};
					this._notifySubscribers();
				}
			}));
			if (finishDetachedSetup()) return;
			unsubs.push(session.onVolumeChange((volume) => {
				if (this._voiceSession !== session) return;
				this._voiceVolume = volume;
				notifyEventListeners(this._voiceVolumeSubscribers, void 0, "Voice volume");
			}));
			if (finishDetachedSetup()) return;
			unsubs.push(session.onTranscript((transcript) => {
				if (this._voiceSession !== session) return;
				this._handleVoiceTranscript(transcript);
			}));
			if (!finishDetachedSetup()) this._onVoiceConnected();
		} catch (error) {
			if (this._voiceSession === session && this._voiceUnsubs === unsubs) {
				try {
					this._disconnectVoice(false);
				} catch (cleanupError) {
					console.error("[assistant-ui] Voice rollback cleanup threw", cleanupError);
				}
				if (replacing && this._voiceSession === void 0) this._onVoiceDisconnected();
			} else finishDetachedSetup();
			throw error;
		}
	}
	_currentAssistantMsg = null;
	_observeVoiceCommit(commit) {
		new Promise((resolve) => resolve(commit())).catch((error) => {
			console.error("[assistant-ui] Voice message commit failed", error);
		});
	}
	_handleVoiceTranscript(transcript) {
		this.ensureInitialized();
		if (transcript.role === "user") {
			this._finishVoiceAssistantMessage();
			this._currentAssistantMsg = null;
			if (transcript.isFinal) this._observeVoiceCommit(() => this._commitVoiceUserMessage({
				id: generateId(),
				role: "user",
				content: [{
					type: "text",
					text: transcript.text
				}],
				metadata: {
					modality: "voice",
					custom: {}
				},
				createdAt: /* @__PURE__ */ new Date(),
				attachments: []
			}));
		} else {
			const status = transcript.isFinal ? {
				type: "complete",
				reason: "stop"
			} : { type: "running" };
			if (!this._currentAssistantMsg) {
				this._currentAssistantMsg = {
					id: generateId(),
					role: "assistant",
					content: [{
						type: "text",
						text: transcript.text
					}],
					metadata: {
						unstable_state: this.state,
						unstable_annotations: [],
						unstable_data: [],
						steps: [],
						modality: "voice",
						custom: {}
					},
					status,
					createdAt: /* @__PURE__ */ new Date()
				};
				this._voiceMessages.push(this._currentAssistantMsg);
			} else {
				const idx = this._voiceMessages.indexOf(this._currentAssistantMsg);
				if (idx === -1) return;
				const updated = {
					...this._currentAssistantMsg,
					content: [{
						type: "text",
						text: transcript.text
					}],
					status
				};
				this._voiceMessages[idx] = updated;
				this._currentAssistantMsg = updated;
			}
			if (transcript.isFinal) {
				const message = this._currentAssistantMsg;
				this._observeVoiceCommit(() => this._commitVoiceMessage(message));
				this._currentAssistantMsg = null;
			}
			this._markVoiceMessagesDirty();
			this._notifySubscribers();
		}
	}
	_commitVoiceUserMessage(message) {
		this._voiceMessages.push(message);
		try {
			return this._commitVoiceMessage(message);
		} finally {
			this._markVoiceMessagesDirty();
			this._notifySubscribers();
		}
	}
	async _appendToVoiceSession(message) {
		const session = this._voiceSession;
		if (!this.voice?.canSendText || !session?.sendText) throw new Error("Cannot send a text message while a voice session is connected");
		const content = message.content.filter((part) => part.type === "text");
		if (message.role !== "user" || message.sourceId != null || message.parentId !== this._resolveAppendParent(this.messages.at(-1)?.id ?? null) || message.attachments?.length || content.length !== message.content.length || !content.some((part) => part.text.trim())) throw new Error("Only a plain text user message can be sent while a voice session is connected");
		const enriched = this.enrichAppendMetadata(message);
		this.ensureInitialized();
		const generation = captureThreadRuntimeGeneration(this);
		try {
			await session.sendText(getThreadMessageText(message));
		} catch (error) {
			if (generation.aborted) return;
			const notSent = new MessageNotSentError();
			notSent.cause = error;
			throw notSent;
		}
		if (generation.aborted) return;
		if (this._voiceSession !== session) throw new MessageNotSentError("The voice session ended before the typed message was recorded");
		this._finishVoiceAssistantMessage(false);
		this._currentAssistantMsg = null;
		await this._commitVoiceUserMessage({
			id: generateId(),
			role: "user",
			content,
			metadata: { custom: { ...enriched.metadata?.custom } },
			createdAt: message.createdAt,
			attachments: []
		});
	}
	_finishVoiceAssistantMessage(notify = true) {
		const last = this._voiceMessages.at(-1);
		if (last?.role === "assistant" && last.status.type === "running") {
			const idx = this._voiceMessages.length - 1;
			this._voiceMessages[idx] = {
				...last,
				status: {
					type: "complete",
					reason: "stop"
				}
			};
			this._observeVoiceCommit(() => this._commitVoiceMessage(this._voiceMessages[idx]));
			this._currentAssistantMsg = null;
			this._markVoiceMessagesDirty();
			if (notify) this._notifySubscribers();
		}
	}
	disconnectVoice() {
		this._disconnectVoice(true);
	}
	_disconnectVoice(fireHook) {
		this._finishVoiceAssistantMessage(false);
		this._currentAssistantMsg = null;
		const unsubs = this._voiceUnsubs.splice(0);
		this._voiceUnsubs = [];
		const session = this._voiceSession;
		this._voiceSession = void 0;
		this.voice = void 0;
		this._voiceVolume = 0;
		const stopSpeaking = this.speech && this._isVoiceMessage(this.speech.messageId) ? this._stopSpeaking : void 0;
		this._voiceMessages = [];
		this._markVoiceMessagesDirty();
		try {
			notifySubscribers([
				...unsubs,
				...stopSpeaking ? [stopSpeaking] : [],
				...session ? [() => session.disconnect()] : [],
				() => notifyEventListeners(this._voiceVolumeSubscribers, void 0, "Voice volume"),
				() => this._notifySubscribers()
			]);
		} finally {
			if (fireHook && session && this._voiceSession === void 0) this._onVoiceDisconnected();
		}
	}
	muteVoice() {
		if (!this._voiceSession) throw new Error("No active voice session");
		this._voiceSession.mute();
		this.voice = {
			...this.voice,
			isMuted: true
		};
		this._notifySubscribers();
	}
	unmuteVoice() {
		if (!this._voiceSession) throw new Error("No active voice session");
		this._voiceSession.unmute();
		this.voice = {
			...this.voice,
			isMuted: false
		};
		this._notifySubscribers();
	}
	ensureInitialized() {
		if (!this._isInitialized) {
			this._isInitialized = true;
			this._notifyEventSubscribers("initialize", {});
		}
	}
	export() {
		return this.repository.export();
	}
	import(data) {
		this.ensureInitialized();
		this.repository.clear();
		this.repository.import(data);
		this._notifySubscribers();
	}
	reset(initialMessages) {
		this.import(ExportedMessageRepository.fromArray(initialMessages ?? []));
	}
	_eventSubscribers = /* @__PURE__ */ new Map();
	unstable_on(event, callback) {
		const wrapped = callback;
		if (event === "modelContextUpdate") return this._contextProvider.subscribe?.(() => notifyEventListeners([wrapped], {}, `Thread runtime "${event}"`)) ?? (() => {});
		let subscribers = this._eventSubscribers.get(event);
		if (!subscribers) {
			subscribers = /* @__PURE__ */ new Set();
			this._eventSubscribers.set(event, subscribers);
		}
		subscribers.add(wrapped);
		if (event === "initialize" && this._isInitialized) queueMicrotask(() => {
			if (subscribers.has(wrapped)) notifyEventListeners([wrapped], {}, `Thread runtime "${event}"`);
		});
		return () => {
			this._eventSubscribers.get(event)?.delete(wrapped);
		};
	}
};
//#endregion
export { BaseThreadRuntimeCore };
