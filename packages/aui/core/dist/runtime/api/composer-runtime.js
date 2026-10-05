import { EventSubscriptionSubject, LazyMemoizeSubject, SKIP_UPDATE, ShallowMemoizeSubject } from "../../subscribable/subscribable.js";
import { EditComposerAttachmentRuntimeImpl, ThreadComposerAttachmentRuntimeImpl } from "./attachment-runtime.js";
//#region src/runtime/api/composer-runtime.ts
const EMPTY_ARRAY = Object.freeze([]);
const EMPTY_OBJECT = Object.freeze({});
const getThreadComposerState = (runtime) => {
	return Object.freeze({
		type: "thread",
		isEditing: runtime?.isEditing ?? false,
		canCancel: runtime?.canCancel ?? false,
		canSend: runtime?.canSend ?? false,
		isEmpty: runtime?.isEmpty ?? true,
		attachments: runtime?.attachments ?? EMPTY_ARRAY,
		text: runtime?.text ?? "",
		role: runtime?.role ?? "user",
		runConfig: runtime?.runConfig ?? EMPTY_OBJECT,
		attachmentAccept: runtime?.attachmentAccept ?? "",
		dictation: runtime?.dictation,
		quote: runtime?.quote,
		queue: runtime?.queue ?? EMPTY_ARRAY,
		submission: runtime?.submission,
		inTransit: runtime?.inTransit ?? EMPTY_ARRAY,
		value: runtime?.text ?? ""
	});
};
const getEditComposerState = (runtime) => {
	return Object.freeze({
		type: "edit",
		isEditing: runtime?.isEditing ?? false,
		canCancel: runtime?.canCancel ?? false,
		canSend: runtime?.canSend ?? false,
		isEmpty: runtime?.isEmpty ?? true,
		text: runtime?.text ?? "",
		role: runtime?.role ?? "user",
		attachments: runtime?.attachments ?? EMPTY_ARRAY,
		runConfig: runtime?.runConfig ?? EMPTY_OBJECT,
		attachmentAccept: runtime?.attachmentAccept ?? "",
		dictation: runtime?.dictation,
		quote: runtime?.quote,
		queue: runtime?.queue ?? EMPTY_ARRAY,
		submission: runtime?.submission,
		inTransit: runtime?.inTransit ?? EMPTY_ARRAY,
		parentId: runtime?.parentId ?? null,
		sourceId: runtime?.sourceId ?? null,
		value: runtime?.text ?? ""
	});
};
var ComposerRuntimeImpl = class {
	get path() {
		return this._core.path;
	}
	_core;
	constructor(_core) {
		this._core = _core;
	}
	__internal_bindMethods() {
		this.setText = this.setText.bind(this);
		this.setRunConfig = this.setRunConfig.bind(this);
		this.getState = this.getState.bind(this);
		this.subscribe = this.subscribe.bind(this);
		this.addAttachment = this.addAttachment.bind(this);
		this.reset = this.reset.bind(this);
		this.clearAttachments = this.clearAttachments.bind(this);
		this.send = this.send.bind(this);
		this.cancel = this.cancel.bind(this);
		this.steerQueueItem = this.steerQueueItem.bind(this);
		this.moveQueueItem = this.moveQueueItem.bind(this);
		this.removeQueueItem = this.removeQueueItem.bind(this);
		this.setRole = this.setRole.bind(this);
		this.getAttachmentByIndex = this.getAttachmentByIndex.bind(this);
		this.startDictation = this.startDictation.bind(this);
		this.stopDictation = this.stopDictation.bind(this);
		this.setQuote = this.setQuote.bind(this);
		this.unstable_on = this.unstable_on.bind(this);
	}
	setText(text) {
		const core = this._core.getState();
		if (!core) throw new Error("Composer is not available");
		core.setText(text);
	}
	setRunConfig(runConfig) {
		const core = this._core.getState();
		if (!core) throw new Error("Composer is not available");
		core.setRunConfig(runConfig);
	}
	addAttachment(fileOrAttachment) {
		const core = this._core.getState();
		if (!core) throw new Error("Composer is not available");
		return core.addAttachment(fileOrAttachment);
	}
	reset() {
		const core = this._core.getState();
		if (!core) throw new Error("Composer is not available");
		return core.reset();
	}
	clearAttachments() {
		const core = this._core.getState();
		if (!core) throw new Error("Composer is not available");
		return core.clearAttachments();
	}
	send(options) {
		const core = this._core.getState();
		if (!core) throw new Error("Composer is not available");
		core.send(options);
	}
	cancel() {
		const core = this._core.getState();
		if (!core) throw new Error("Composer is not available");
		core.cancel();
	}
	steerQueueItem(queueItemId) {
		this.moveQueueItem(queueItemId, {
			lane: "steer",
			insertAfter: null
		});
	}
	moveQueueItem(queueItemId, placement) {
		const core = this._core.getState();
		if (!core) throw new Error("Composer is not available");
		core.moveQueueItem(queueItemId, placement);
	}
	editQueueItem(queueItemId, message) {
		const core = this._core.getState();
		if (!core) throw new Error("Composer is not available");
		core.editQueueItem(queueItemId, message);
	}
	removeQueueItem(queueItemId) {
		const core = this._core.getState();
		if (!core) throw new Error("Composer is not available");
		core.removeQueueItem(queueItemId);
	}
	setRole(role) {
		const core = this._core.getState();
		if (!core) throw new Error("Composer is not available");
		core.setRole(role);
	}
	startDictation() {
		const core = this._core.getState();
		if (!core) throw new Error("Composer is not available");
		core.startDictation();
	}
	stopDictation() {
		const core = this._core.getState();
		if (!core) throw new Error("Composer is not available");
		core.stopDictation();
	}
	setQuote(quote) {
		const core = this._core.getState();
		if (!core) throw new Error("Composer is not available");
		core.setQuote(quote);
	}
	subscribe(callback) {
		return this._core.subscribe(callback);
	}
	_eventSubscriptionSubjects = /* @__PURE__ */ new Map();
	unstable_on(event, callback) {
		let subject = this._eventSubscriptionSubjects.get(event);
		if (!subject) {
			subject = new EventSubscriptionSubject({
				event,
				binding: this._core
			});
			this._eventSubscriptionSubjects.set(event, subject);
		}
		return subject.subscribe(callback);
	}
};
var ThreadComposerRuntimeImpl = class extends ComposerRuntimeImpl {
	get path() {
		return this._core.path;
	}
	get type() {
		return "thread";
	}
	_getState;
	constructor(core) {
		const stateBinding = new LazyMemoizeSubject({
			path: core.path,
			getState: () => getThreadComposerState(core.getState()),
			subscribe: (callback) => core.subscribe(callback)
		});
		super({
			path: core.path,
			getState: () => core.getState(),
			subscribe: (callback) => stateBinding.subscribe(callback)
		});
		this._getState = stateBinding.getState.bind(stateBinding);
		this.__internal_bindMethods();
	}
	getState() {
		return this._getState();
	}
	getAttachmentByIndex(idx) {
		return new ThreadComposerAttachmentRuntimeImpl(new ShallowMemoizeSubject({
			path: {
				...this.path,
				attachmentSource: "thread-composer",
				attachmentSelector: {
					type: "index",
					index: idx
				},
				ref: `${this.path.ref}.attachments[${idx}]`
			},
			getState: () => {
				const attachment = this.getState().attachments[idx];
				if (!attachment) return SKIP_UPDATE;
				return {
					...attachment,
					source: "thread-composer"
				};
			},
			subscribe: (callback) => this._core.subscribe(callback)
		}), this._core);
	}
};
var EditComposerRuntimeImpl = class extends ComposerRuntimeImpl {
	get path() {
		return this._core.path;
	}
	get type() {
		return "edit";
	}
	_getState;
	_beginEdit;
	constructor(core, _beginEdit) {
		const stateBinding = new LazyMemoizeSubject({
			path: core.path,
			getState: () => getEditComposerState(core.getState()),
			subscribe: (callback) => core.subscribe(callback)
		});
		super({
			path: core.path,
			getState: () => core.getState(),
			subscribe: (callback) => stateBinding.subscribe(callback)
		});
		this._beginEdit = _beginEdit;
		this._getState = stateBinding.getState.bind(stateBinding);
		this.__internal_bindMethods();
	}
	__internal_bindMethods() {
		super.__internal_bindMethods();
		this.beginEdit = this.beginEdit.bind(this);
	}
	getState() {
		return this._getState();
	}
	beginEdit() {
		this._beginEdit();
	}
	getAttachmentByIndex(idx) {
		return new EditComposerAttachmentRuntimeImpl(new ShallowMemoizeSubject({
			path: {
				...this.path,
				attachmentSource: "edit-composer",
				attachmentSelector: {
					type: "index",
					index: idx
				},
				ref: `${this.path.ref}.attachments[${idx}]`
			},
			getState: () => {
				const attachment = this.getState().attachments[idx];
				if (!attachment) return SKIP_UPDATE;
				return {
					...attachment,
					source: "edit-composer"
				};
			},
			subscribe: (callback) => this._core.subscribe(callback)
		}), this._core);
	}
};
//#endregion
export { ComposerRuntimeImpl, EditComposerRuntimeImpl, ThreadComposerRuntimeImpl };
