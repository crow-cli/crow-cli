import { BaseSubscribable } from "../../subscribable/subscribable.js";
//#region src/runtimes/inert/InertThreadRuntimeCore.ts
const createInertComposer = (error, isEditing) => ({
	attachments: [],
	attachmentAccept: "*",
	async addAttachment() {
		throw error;
	},
	async removeAttachment() {
		throw error;
	},
	isEditing,
	canCancel: false,
	canSend: false,
	isEmpty: true,
	text: "",
	setText() {
		throw error;
	},
	role: "user",
	setRole() {
		throw error;
	},
	runConfig: {},
	setRunConfig() {
		throw error;
	},
	async reset() {},
	async clearAttachments() {},
	send() {
		throw error;
	},
	cancel() {},
	queue: [],
	moveQueueItem() {},
	editQueueItem() {},
	removeQueueItem() {},
	dictation: void 0,
	startDictation() {
		throw error;
	},
	stopDictation() {},
	quote: void 0,
	setQuote() {
		throw error;
	},
	subscribe() {
		return () => {};
	},
	unstable_on() {
		return () => {};
	}
});
var InertThreadRuntimeCore = class extends BaseSubscribable {
	switchToBranch() {
		throw this.error;
	}
	append() {
		throw this.error;
	}
	deleteMessage() {
		throw this.error;
	}
	startRun() {
		throw this.error;
	}
	resumeRun() {
		throw this.error;
	}
	cancelRun() {
		throw this.error;
	}
	unstable_notifySessionReset() {
		throw this.error;
	}
	addToolResult() {
		throw this.error;
	}
	resumeToolCall() {
		throw this.error;
	}
	respondToToolApproval() {
		throw this.error;
	}
	async unstable_recordToolInteraction(_options) {
		throw this.error;
	}
	speak() {
		throw this.error;
	}
	stopSpeaking() {
		throw this.error;
	}
	connectVoice() {
		throw this.error;
	}
	disconnectVoice() {
		throw this.error;
	}
	muteVoice() {
		throw this.error;
	}
	unmuteVoice() {
		throw this.error;
	}
	submitFeedback() {
		throw this.error;
	}
	exportExternalState() {
		throw this.error;
	}
	importExternalState() {
		throw this.error;
	}
	beginEdit() {
		throw this.error;
	}
	import() {
		throw this.error;
	}
	reset() {
		throw this.error;
	}
	getModelContext() {
		return {};
	}
	getEditComposer() {}
	getVoiceVolume = () => 0;
	subscribeVoiceVolume = () => () => {};
	speech = void 0;
	voice = void 0;
	capabilities = {
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
	isDisabled = false;
	isSendDisabled = false;
	state = null;
	suggestions = [];
	extras = void 0;
	unstable_on() {
		return () => {};
	}
};
//#endregion
export { InertThreadRuntimeCore, createInertComposer };
