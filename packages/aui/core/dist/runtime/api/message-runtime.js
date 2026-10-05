import { getThreadMessageText } from "../../utils/text.js";
import { NestedSubscriptionSubject, SKIP_UPDATE, ShallowMemoizeSubject } from "../../subscribable/subscribable.js";
import { symbolInnerMessage } from "../utils/external-store-message.js";
import { toMessagePartStatus } from "../../utils/normalizePartStatus.js";
import { reportRunFailure } from "../../utils/report-run-failure.js";
import { MessageAttachmentRuntimeImpl } from "./attachment-runtime.js";
import { EditComposerRuntimeImpl } from "./composer-runtime.js";
import { MessagePartRuntimeImpl } from "./message-part-runtime.js";
//#region src/runtime/api/message-runtime.ts
const getMessagePartState = (message, partIndex) => {
	const part = message.content[partIndex];
	if (!part) return SKIP_UPDATE;
	const status = toMessagePartStatus(message, partIndex, part);
	return Object.freeze({
		...part,
		[symbolInnerMessage]: part[symbolInnerMessage],
		status
	});
};
var MessageRuntimeImpl = class {
	get path() {
		return this._core.path;
	}
	_core;
	_threadBinding;
	constructor(_core, _threadBinding) {
		this._core = _core;
		this._threadBinding = _threadBinding;
		this.composer = new EditComposerRuntimeImpl(new NestedSubscriptionSubject({
			path: {
				...this.path,
				ref: `${this.path.ref}.composer`,
				composerSource: "edit"
			},
			getState: this._getEditComposerRuntimeCore,
			subscribe: (callback) => this._threadBinding.subscribe(callback)
		}), () => this._threadBinding.getState().beginEdit(this._core.getState().id));
		this.__internal_bindMethods();
	}
	__internal_bindMethods() {
		this.reload = this.reload.bind(this);
		this.delete = this.delete.bind(this);
		this.getState = this.getState.bind(this);
		this.subscribe = this.subscribe.bind(this);
		this.getMessagePartByIndex = this.getMessagePartByIndex.bind(this);
		this.getMessagePartByToolCallId = this.getMessagePartByToolCallId.bind(this);
		this.getAttachmentByIndex = this.getAttachmentByIndex.bind(this);
		this.unstable_getCopyText = this.unstable_getCopyText.bind(this);
		this.speak = this.speak.bind(this);
		this.stopSpeaking = this.stopSpeaking.bind(this);
		this.submitFeedback = this.submitFeedback.bind(this);
		this.switchToBranch = this.switchToBranch.bind(this);
	}
	composer;
	_getEditComposerRuntimeCore = () => {
		return this._threadBinding.getState().getEditComposer(this._core.getState().id);
	};
	getState() {
		return this._core.getState();
	}
	delete() {
		const state = this._core.getState();
		return this._threadBinding.getState().deleteMessage(state.id);
	}
	reload(reloadConfig = {}) {
		const editComposerRuntimeCore = this._getEditComposerRuntimeCore();
		const composerRuntimeCore = editComposerRuntimeCore ?? this._threadBinding.getState().composer;
		const composer = editComposerRuntimeCore ?? composerRuntimeCore;
		const { runConfig = composer.runConfig } = reloadConfig;
		const state = this._core.getState();
		if (state.role !== "assistant") throw new Error("Can only reload assistant messages");
		reportRunFailure("Message reload", this._threadBinding.getState().startRun({
			parentId: state.parentId,
			sourceId: state.id,
			runConfig
		}));
	}
	speak() {
		const state = this._core.getState();
		return this._threadBinding.getState().speak(state.id);
	}
	stopSpeaking() {
		const state = this._core.getState();
		if (this._threadBinding.getState().speech?.messageId === state.id) this._threadBinding.getState().stopSpeaking();
		else throw new Error("Message is not being spoken");
	}
	submitFeedback({ type, comment }) {
		const state = this._core.getState();
		this._threadBinding.getState().submitFeedback({
			messageId: state.id,
			type,
			...comment !== void 0 ? { comment } : void 0
		});
	}
	switchToBranch({ position, branchId }) {
		const state = this._core.getState();
		if (branchId && position) throw new Error("May not specify both branchId and position");
		else if (!branchId && !position) throw new Error("Must specify either branchId or position");
		const branches = this._threadBinding.getState().getBranches(state.id);
		let targetBranch = branchId;
		if (position === "previous") targetBranch = branches[state.branchNumber - 2];
		else if (position === "next") targetBranch = branches[state.branchNumber];
		if (!targetBranch) throw new Error("Branch not found");
		this._threadBinding.getState().switchToBranch(targetBranch);
	}
	unstable_getCopyText() {
		return getThreadMessageText(this.getState());
	}
	subscribe(callback) {
		return this._core.subscribe(callback);
	}
	getMessagePartByIndex(idx) {
		if (idx < 0) throw new Error("Message part index must be >= 0");
		return new MessagePartRuntimeImpl(new ShallowMemoizeSubject({
			path: {
				...this.path,
				ref: `${this.path.ref}.content[${idx}]`,
				messagePartSelector: {
					type: "index",
					index: idx
				}
			},
			getState: () => {
				return getMessagePartState(this.getState(), idx);
			},
			subscribe: (callback) => this._core.subscribe(callback)
		}), this._core, this._threadBinding);
	}
	getMessagePartByToolCallId(toolCallId) {
		return new MessagePartRuntimeImpl(new ShallowMemoizeSubject({
			path: {
				...this.path,
				ref: `${this.path.ref}.content[toolCallId=${JSON.stringify(toolCallId)}]`,
				messagePartSelector: {
					type: "toolCallId",
					toolCallId
				}
			},
			getState: () => {
				const state = this._core.getState();
				const idx = state.content.findIndex((part) => part.type === "tool-call" && part.toolCallId === toolCallId);
				if (idx === -1) return SKIP_UPDATE;
				return getMessagePartState(state, idx);
			},
			subscribe: (callback) => this._core.subscribe(callback)
		}), this._core, this._threadBinding);
	}
	getAttachmentByIndex(idx) {
		return new MessageAttachmentRuntimeImpl(new ShallowMemoizeSubject({
			path: {
				...this.path,
				ref: `${this.path.ref}.attachments[${idx}]`,
				attachmentSource: "message",
				attachmentSelector: {
					type: "index",
					index: idx
				}
			},
			getState: () => {
				const attachment = this.getState().attachments?.[idx];
				if (!attachment) return SKIP_UPDATE;
				return {
					...attachment,
					source: "message"
				};
			},
			subscribe: (callback) => this._core.subscribe(callback)
		}));
	}
};
//#endregion
export { MessageRuntimeImpl };
