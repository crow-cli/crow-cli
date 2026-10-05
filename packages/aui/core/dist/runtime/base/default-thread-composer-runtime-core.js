import { EMPTY_QUEUE_ITEMS } from "../queue/queue-item.js";
import { getThreadRuntimeCoreIsRunning } from "../api/thread-runtime.js";
import { BaseComposerRuntimeCore } from "./base-composer-runtime-core.js";
//#region src/runtime/base/default-thread-composer-runtime-core.ts
const isCancelable = (runtime) => {
	if (!runtime.capabilities?.cancel) return false;
	return getThreadRuntimeCoreIsRunning(runtime);
};
var DefaultThreadComposerRuntimeCore = class extends BaseComposerRuntimeCore {
	get canCancel() {
		return this.isSubmitting || isCancelable(this.runtime);
	}
	get canSend() {
		if (this.isEmpty || this.runtime.isSendDisabled || this.isSubmitting) return false;
		const voice = this.runtime.voice;
		if (!voice) return true;
		return voice.canSendText && this.role === "user" && this.attachments.length === 0;
	}
	cancel() {
		if (!this.isSubmitting) {
			super.cancel();
			return;
		}
		this.cancelSubmission();
		if (isCancelable(this.runtime)) super.cancel();
	}
	threadMessageIds(role) {
		return this.runtime.messages.filter((message) => message.role === role).map((message) => message.id);
	}
	_queueCache;
	get queue() {
		const steer = this.runtime.getSteerQueueItems?.() ?? EMPTY_QUEUE_ITEMS;
		const queue = this.runtime.getQueueItems?.() ?? EMPTY_QUEUE_ITEMS;
		const cache = this._queueCache;
		if (cache && cache.steer === steer && cache.queue === queue) return cache.flat;
		const flat = steer.length === 0 ? queue : queue.length === 0 ? steer : [...steer, ...queue];
		this._queueCache = {
			steer,
			queue,
			flat
		};
		return flat;
	}
	moveQueueItem(queueItemId, placement) {
		this.runtime.moveQueueItem?.(queueItemId, placement);
	}
	editQueueItem(queueItemId, message) {
		this.runtime.editQueueItem?.(queueItemId, message);
	}
	removeQueueItem(queueItemId) {
		this.runtime.removeQueueItem?.(queueItemId);
	}
	getAttachmentAdapter() {
		return this.runtime.adapters?.attachments;
	}
	getDictationAdapter() {
		return this.runtime.adapters?.dictation;
	}
	runtime;
	constructor(runtime) {
		super();
		this.runtime = runtime;
		this.connect();
	}
	connect() {
		let lastCanCancel = false;
		let lastIsSendDisabled = this.runtime.isSendDisabled;
		let lastVoiceInput = this.runtime.voice?.canSendText;
		let lastQueue = this.queue;
		return this.runtime.subscribe(() => {
			this.settleInTransit();
			let changed = false;
			const nextCanCancel = this.canCancel;
			if (lastCanCancel !== nextCanCancel) {
				lastCanCancel = nextCanCancel;
				changed = true;
			}
			if (lastIsSendDisabled !== this.runtime.isSendDisabled) {
				lastIsSendDisabled = this.runtime.isSendDisabled;
				changed = true;
			}
			const nextVoiceInput = this.runtime.voice?.canSendText;
			if (lastVoiceInput !== nextVoiceInput) {
				lastVoiceInput = nextVoiceInput;
				changed = true;
			}
			if (lastQueue !== this.queue) {
				lastQueue = this.queue;
				changed = true;
			}
			if (changed) this._notifySubscribers();
		});
	}
	async handleSend(message, options) {
		return this.runtime.append({
			...message,
			parentId: this.runtime.messages.at(-1)?.id ?? null,
			sourceId: null,
			startRun: options?.startRun,
			steer: options?.steer
		});
	}
	async handleCancel() {
		this.runtime.cancelRun();
	}
};
//#endregion
export { DefaultThreadComposerRuntimeCore };
