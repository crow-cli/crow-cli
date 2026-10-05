import { liftNonTextParts } from "../../adapters/attachment.js";
import { getThreadMessageText } from "../../utils/text.js";
import { BaseComposerRuntimeCore } from "./base-composer-runtime-core.js";
//#region src/runtime/base/default-edit-composer-runtime-core.ts
var DefaultEditComposerRuntimeCore = class extends BaseComposerRuntimeCore {
	get canCancel() {
		return true;
	}
	get detachesDraftOnSend() {
		return false;
	}
	get canSend() {
		return !this.isEmpty && !this.runtime.voice && !this.isSubmitting;
	}
	getAttachmentAdapter() {
		return this.runtime.adapters?.attachments;
	}
	getDictationAdapter() {
		return this.runtime.adapters?.dictation;
	}
	_nonTextPassthrough;
	_parentId;
	_sourceId;
	runtime;
	endEditCallback;
	_ended = false;
	constructor(runtime, endEditCallback, { parentId, message }) {
		super();
		this.runtime = runtime;
		let lastHasVoice = runtime.voice !== void 0;
		const unsubscribe = runtime.subscribe(() => {
			const hasVoice = runtime.voice !== void 0;
			if (hasVoice === lastHasVoice) return;
			lastHasVoice = hasVoice;
			this._notifySubscribers();
		});
		this.endEditCallback = () => {
			unsubscribe();
			endEditCallback();
		};
		this._parentId = parentId;
		this._sourceId = message.id;
		this.setText(getThreadMessageText(message));
		this.setRole(message.role);
		let attachments;
		if (message.role === "user") {
			attachments = [...message.attachments ?? [], ...liftNonTextParts(message.content)];
			this._nonTextPassthrough = [];
		} else {
			attachments = message.attachments ?? [];
			this._nonTextPassthrough = message.content.filter((p) => p.type !== "text");
		}
		this.setAttachments(attachments);
		this.setRunConfig({ ...runtime.composer.runConfig });
	}
	get parentId() {
		return this._parentId;
	}
	get sourceId() {
		return this._sourceId;
	}
	async handleSend(message, options) {
		const content = this._nonTextPassthrough.length > 0 ? [...message.content, ...this._nonTextPassthrough] : message.content;
		const appendTask = this.runtime.append({
			...message,
			content,
			parentId: this._parentId,
			sourceId: this._sourceId,
			startRun: options?.startRun
		});
		this.handleCancel();
		return appendTask;
	}
	handleCancel() {
		if (this._ended) return;
		this._ended = true;
		this.reset().catch((error) => {
			console.error("[assistant-ui] Failed to clear cancelled edit", error);
		});
		this.endEditCallback();
		this._notifySubscribers();
	}
};
//#endregion
export { DefaultEditComposerRuntimeCore };
