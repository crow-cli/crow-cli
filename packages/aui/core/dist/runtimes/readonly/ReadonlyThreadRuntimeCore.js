import { InertThreadRuntimeCore, createInertComposer } from "../inert/InertThreadRuntimeCore.js";
//#region src/runtimes/readonly/ReadonlyThreadRuntimeCore.ts
const READONLY_THREAD_ERROR = /* @__PURE__ */ new Error("This is a readonly thread. You cannot perform mutations on readonly threads.");
var ReadonlyThreadRuntimeCore = class extends InertThreadRuntimeCore {
	get error() {
		return READONLY_THREAD_ERROR;
	}
	_messages = [];
	get messages() {
		return this._messages;
	}
	setMessages(messages) {
		if (this._messages === messages) return;
		this._messages = messages;
		this._notifySubscribers();
	}
	getMessageById(messageId) {
		const idx = this._messages.findIndex((m) => m.id === messageId);
		if (idx === -1) return void 0;
		return {
			parentId: this._messages[idx - 1]?.id ?? null,
			message: this._messages[idx],
			index: idx
		};
	}
	getBranches(messageId) {
		if (this._messages.findIndex((m) => m.id === messageId) === -1) return [];
		return [messageId];
	}
	export() {
		return { messages: this._messages.map((message, idx) => ({
			message,
			parentId: this._messages[idx - 1]?.id ?? null
		})) };
	}
	composer = {
		...createInertComposer(READONLY_THREAD_ERROR, false),
		async addAttachment(_fileOrAttachment) {},
		setText(_value) {},
		send(_options) {},
		setQuote(_quote) {}
	};
	isLoading = false;
	isDisabled = true;
	isSendDisabled = true;
	switchToBranch() {}
	append() {}
	deleteMessage() {}
	startRun() {}
	resumeRun() {}
	cancelRun() {}
	unstable_notifySessionReset() {}
	addToolResult() {}
	resumeToolCall() {}
	async respondToToolApproval() {}
	async unstable_recordToolInteraction(_options) {}
	speak() {}
	stopSpeaking() {}
	connectVoice() {}
	disconnectVoice() {}
	muteVoice() {}
	unmuteVoice() {}
	submitFeedback() {}
	importExternalState() {}
	beginEdit() {}
	import() {}
	reset() {}
};
//#endregion
export { ReadonlyThreadRuntimeCore };
