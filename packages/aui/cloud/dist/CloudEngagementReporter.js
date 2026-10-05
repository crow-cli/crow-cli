//#region src/CloudEngagementReporter.ts
const MAX_REMEMBERED_THREADS = 256;
function remember(map, threadId, value) {
	map.delete(threadId);
	map.set(threadId, value);
	if (map.size > MAX_REMEMBERED_THREADS) map.delete(map.keys().next().value);
}
function mark(set, threadId) {
	set.delete(threadId);
	set.add(threadId);
	if (set.size > MAX_REMEMBERED_THREADS) set.delete(set.values().next().value);
}
const passThroughIds = (threadId, messageId) => ({
	thread_id: threadId,
	...messageId !== void 0 ? { message_id: messageId } : void 0
});
/**
* Derives engagement events from what a chat integration observes and keeps
* the per thread state the events need: a run's start for the stop duration,
* a run's end for the time to the next message, one error and one suggestion
* list per run or thread. A started run is kept until it ends or stops; the
* rest is kept for the 256 most recently touched threads, so a long session
* does not grow it without bound. Delivery goes through the cloud's event
* buffer, so a disabled telemetry setting drops everything here as well.
*/
var CloudEngagementReporter = class {
	runStartedAt = /* @__PURE__ */ new Map();
	runEndedAt = /* @__PURE__ */ new Map();
	shownErrors = /* @__PURE__ */ new Set();
	shownSuggestions = /* @__PURE__ */ new Set();
	getCloud;
	resolveIds;
	constructor(cloud, resolveIds = passThroughIds) {
		this.getCloud = typeof cloud === "function" ? cloud : () => cloud;
		this.resolveIds = resolveIds;
	}
	runStarted(threadId) {
		this.runStartedAt.set(threadId, Date.now());
		this.shownErrors.delete(threadId);
	}
	runEnded(threadId) {
		this.runStartedAt.delete(threadId);
		remember(this.runEndedAt, threadId, Date.now());
	}
	/** Reported once per started run, with the time the run had been going. */
	runStopped(threadId) {
		const startedAt = this.runStartedAt.get(threadId);
		if (startedAt === void 0) return;
		const stoppedAt = Date.now();
		this.runStartedAt.delete(threadId);
		remember(this.runEndedAt, threadId, stoppedAt);
		this.track("run_stopped", threadId, void 0, { value: Math.max(0, stoppedAt - startedAt) });
	}
	/** Carries the time since the previous run of the thread ended, when known. */
	messageSent(threadId, init) {
		const previousRunEndedAt = this.runEndedAt.get(threadId);
		this.track("message_sent", threadId, init.messageId, {
			props: {
				chars: init.chars,
				attachments: init.attachments
			},
			...previousRunEndedAt !== void 0 ? { value: Math.max(0, Date.now() - previousRunEndedAt) } : void 0
		}, { awaitThread: true });
	}
	messageEdited(threadId, init) {
		this.track("message_edited", threadId, init.messageId, { props: { chars: init.chars } });
	}
	messageRegenerated(threadId, messageId) {
		this.track("message_regenerated", threadId, messageId);
	}
	/** Reported once per run, so a retried render of the same error stays one event. */
	errorShown(threadId, init) {
		if (this.shownErrors.has(threadId)) return;
		mark(this.shownErrors, threadId);
		this.track("error_shown", threadId, init.messageId, { props: { reason: init.reason } });
	}
	/** Reported once per thread, with the number of suggestions on offer. */
	suggestionsShown(threadId, count) {
		if (this.shownSuggestions.has(threadId)) return;
		mark(this.shownSuggestions, threadId);
		this.track("suggestions_shown", threadId, void 0, { value: count });
	}
	suggestionClicked(threadId) {
		this.track("suggestion_clicked", threadId);
	}
	attachmentAdded(threadId, init) {
		this.track("attachment_added", threadId, init.messageId, { ...init.contentType ? { props: { type: init.contentType } } : void 0 });
	}
	attachmentFailed(threadId, init) {
		this.track("attachment_failed", threadId, init.messageId, { ...init.contentType ? { props: { type: init.contentType } } : void 0 });
	}
	voiceStarted(threadId) {
		this.track("voice_started", threadId);
	}
	speechStarted(threadId, messageId) {
		this.track("speech_started", threadId, messageId);
	}
	branchSwitched(threadId, messageId) {
		this.track("branch_switched", threadId, messageId);
	}
	messageCopied(threadId, messageId) {
		this.track("message_copied", threadId, messageId);
	}
	toolApproved(threadId, messageId, toolCallId, toolName) {
		this.track("tool_approved", threadId, messageId, { props: {
			toolCallId,
			toolName
		} });
	}
	toolRejected(threadId, messageId, toolCallId, toolName) {
		this.track("tool_rejected", threadId, messageId, { props: {
			toolCallId,
			toolName
		} });
	}
	/** Reported only for a thread the cloud already knows. */
	threadSwitched(threadId) {
		this.track("thread_switched", threadId);
	}
	track(kind, threadId, messageId, init = {}, options = { awaitThread: false }) {
		Promise.resolve().then(() => this.resolveIds(threadId, messageId, options)).then((ids) => {
			if (!ids) return;
			if (kind === "thread_switched" && !ids.thread_id) return;
			this.getCloud().events.track({
				kind,
				...init,
				...ids
			});
		}).catch(() => {});
	}
};
//#endregion
export { CloudEngagementReporter };
