import { EventSubscriptionSubject, NestedSubscriptionSubject, SKIP_UPDATE, ShallowMemoizeSubject, runCleanups } from "../../subscribable/subscribable.js";
import { symbolInnerMessage } from "../utils/external-store-message.js";
import { reportRunFailure } from "../../utils/report-run-failure.js";
import { ThreadComposerRuntimeImpl } from "./composer-runtime.js";
import { MessageRuntimeImpl } from "./message-runtime.js";
//#region src/runtime/api/thread-runtime.ts
const toResumeRunConfig = (message) => {
	return {
		parentId: message.parentId ?? null,
		sourceId: message.sourceId ?? null,
		runConfig: message.runConfig ?? {},
		...message.stream ? { stream: message.stream } : {}
	};
};
const toStartRunConfig = (message) => {
	return {
		parentId: message.parentId ?? null,
		sourceId: message.sourceId ?? null,
		runConfig: message.runConfig ?? {}
	};
};
const toAppendMessage = (messages, message) => {
	if (typeof message === "string") return {
		createdAt: /* @__PURE__ */ new Date(),
		parentId: messages.at(-1)?.id ?? null,
		sourceId: null,
		runConfig: {},
		role: "user",
		content: [{
			type: "text",
			text: message
		}],
		attachments: [],
		metadata: { custom: {} }
	};
	return {
		createdAt: message.createdAt ?? /* @__PURE__ */ new Date(),
		parentId: message.parentId === void 0 ? messages.at(-1)?.id ?? null : message.parentId,
		sourceId: message.sourceId ?? null,
		role: message.role ?? "user",
		content: message.content,
		attachments: message.attachments ?? [],
		metadata: message.metadata ?? { custom: {} },
		runConfig: message.runConfig ?? {},
		startRun: message.startRun
	};
};
/**
* The canonical `isRunning` derivation. A runtime that tracks run state itself
* reports it directly; the rest fall back to the trailing assistant message.
*/
const getThreadRuntimeCoreIsRunning = (runtime) => {
	if (runtime.isRunning !== void 0) return runtime.isRunning;
	const lastMessage = runtime.messages.at(-1);
	return lastMessage?.role === "assistant" && lastMessage.status.type === "running";
};
const getThreadState = (runtime, threadListItemState) => {
	return Object.freeze({
		threadId: threadListItemState.id,
		metadata: threadListItemState,
		capabilities: runtime.capabilities,
		isDisabled: runtime.isDisabled,
		isLoading: runtime.isLoading,
		isRunning: getThreadRuntimeCoreIsRunning(runtime),
		messages: runtime.messages,
		state: runtime.state,
		suggestions: runtime.suggestions,
		extras: runtime.extras,
		speech: runtime.speech,
		voice: runtime.voice
	});
};
var ThreadRuntimeImpl = class {
	get path() {
		return this._threadBinding.path;
	}
	get __internal_threadBinding() {
		return this._threadBinding;
	}
	_threadBinding;
	_stateBinding;
	constructor(threadBinding, threadListItemBinding) {
		const stateBinding = new ShallowMemoizeSubject({
			path: threadBinding.path,
			getState: () => getThreadState(threadBinding.getState(), threadListItemBinding.getState()),
			subscribe: (callback) => {
				const sub1 = threadBinding.subscribe(callback);
				const sub2 = threadListItemBinding.subscribe(callback);
				return () => runCleanups([sub1, sub2]);
			}
		});
		this._stateBinding = stateBinding;
		this._threadBinding = {
			path: threadBinding.path,
			getState: () => threadBinding.getState(),
			getStateState: () => stateBinding.getState(),
			outerSubscribe: (callback) => threadBinding.outerSubscribe(callback),
			subscribe: (callback) => threadBinding.subscribe(callback)
		};
		this.composer = new ThreadComposerRuntimeImpl(new NestedSubscriptionSubject({
			path: {
				...this.path,
				ref: `${this.path.ref}.composer`,
				composerSource: "thread"
			},
			getState: () => this._threadBinding.getState().composer,
			subscribe: (callback) => this._threadBinding.subscribe(callback)
		}));
		this.__internal_bindMethods();
	}
	__internal_bindMethods() {
		this.append = this.append.bind(this);
		this.deleteMessage = this.deleteMessage.bind(this);
		this.resumeRun = this.resumeRun.bind(this);
		this.importExternalState = this.importExternalState.bind(this);
		this.exportExternalState = this.exportExternalState.bind(this);
		this.startRun = this.startRun.bind(this);
		this.cancelRun = this.cancelRun.bind(this);
		this.unstable_notifySessionReset = this.unstable_notifySessionReset.bind(this);
		this.stopSpeaking = this.stopSpeaking.bind(this);
		this.connectVoice = this.connectVoice.bind(this);
		this.disconnectVoice = this.disconnectVoice.bind(this);
		this.muteVoice = this.muteVoice.bind(this);
		this.unmuteVoice = this.unmuteVoice.bind(this);
		this.getVoiceVolume = this.getVoiceVolume.bind(this);
		this.subscribeVoiceVolume = this.subscribeVoiceVolume.bind(this);
		this.export = this.export.bind(this);
		this.import = this.import.bind(this);
		this.reset = this.reset.bind(this);
		this.getMessageByIndex = this.getMessageByIndex.bind(this);
		this.getMessageById = this.getMessageById.bind(this);
		this.subscribe = this.subscribe.bind(this);
		this.unstable_on = this.unstable_on.bind(this);
		this.getModelContext = this.getModelContext.bind(this);
		this.getState = this.getState.bind(this);
	}
	composer;
	getState() {
		return this._threadBinding.getStateState();
	}
	append(message) {
		reportRunFailure("Message append", this._threadBinding.getState().append(toAppendMessage(this._threadBinding.getState().messages, message)));
	}
	deleteMessage(messageId) {
		return this._threadBinding.getState().deleteMessage(messageId);
	}
	subscribe(callback) {
		return this._stateBinding.subscribe(callback);
	}
	getModelContext() {
		return this._threadBinding.getState().getModelContext();
	}
	startRun(config) {
		return this._threadBinding.getState().startRun(toStartRunConfig(config));
	}
	resumeRun(config) {
		return this._threadBinding.getState().resumeRun(toResumeRunConfig(config));
	}
	exportExternalState() {
		return this._threadBinding.getState().exportExternalState();
	}
	importExternalState(state) {
		this._threadBinding.getState().importExternalState(state);
	}
	cancelRun() {
		this._threadBinding.getState().cancelRun();
	}
	unstable_notifySessionReset() {
		this._threadBinding.getState().unstable_notifySessionReset();
	}
	stopSpeaking() {
		return this._threadBinding.getState().stopSpeaking();
	}
	connectVoice() {
		this._threadBinding.getState().connectVoice();
	}
	disconnectVoice() {
		this._threadBinding.getState().disconnectVoice();
	}
	getVoiceVolume() {
		return this._threadBinding.getState().getVoiceVolume();
	}
	subscribeVoiceVolume(callback) {
		return this._threadBinding.getState().subscribeVoiceVolume(callback);
	}
	muteVoice() {
		this._threadBinding.getState().muteVoice();
	}
	unmuteVoice() {
		this._threadBinding.getState().unmuteVoice();
	}
	export() {
		return this._threadBinding.getState().export();
	}
	import(data) {
		this._threadBinding.getState().import(data);
	}
	reset(initialMessages) {
		this._threadBinding.getState().reset(initialMessages);
	}
	getMessageByIndex(idx) {
		if (idx < 0) throw new Error("Message index must be >= 0");
		return this._getMessageRuntime({
			...this.path,
			ref: `${this.path.ref}.messages[${idx}]`,
			messageSelector: {
				type: "index",
				index: idx
			}
		}, () => {
			const messages = this._threadBinding.getState().messages;
			const message = messages[idx];
			if (!message) return void 0;
			return {
				message,
				parentId: messages[idx - 1]?.id ?? null,
				index: idx
			};
		});
	}
	getMessageById(messageId) {
		return this._getMessageRuntime({
			...this.path,
			ref: `${this.path.ref}.messages[messageId=${JSON.stringify(messageId)}]`,
			messageSelector: {
				type: "messageId",
				messageId
			}
		}, () => this._threadBinding.getState().getMessageById(messageId));
	}
	_getMessageRuntime(path, callback) {
		return new MessageRuntimeImpl(new ShallowMemoizeSubject({
			path,
			getState: () => {
				const { message, parentId, index } = callback() ?? {};
				const { messages, speech: speechState } = this._threadBinding.getState();
				if (!message || parentId === void 0 || index === void 0) return SKIP_UPDATE;
				const branches = this._threadBinding.getState().getBranches(message.id);
				return {
					...message,
					[symbolInnerMessage]: message[symbolInnerMessage],
					index,
					isLast: messages.at(-1)?.id === message.id,
					parentId,
					branchNumber: branches.indexOf(message.id) + 1,
					branchCount: branches.length,
					speech: speechState?.messageId === message.id ? speechState : void 0
				};
			},
			subscribe: (callback) => this._threadBinding.subscribe(callback)
		}), this._threadBinding);
	}
	_eventSubscriptionSubjects = /* @__PURE__ */ new Map();
	unstable_on(event, callback) {
		let subject = this._eventSubscriptionSubjects.get(event);
		if (!subject) {
			subject = new EventSubscriptionSubject({
				event,
				binding: this._threadBinding,
				notifyOnRebind: event === "modelContextUpdate"
			});
			this._eventSubscriptionSubjects.set(event, subject);
		}
		return subject.subscribe(callback);
	}
};
//#endregion
export { ThreadRuntimeImpl, getThreadRuntimeCoreIsRunning, getThreadState };
