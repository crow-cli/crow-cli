import { generateId } from "../../utils/id.js";
import { fileMatchesAccept } from "../../adapters/attachment.js";
import { notifyEventListeners } from "../../utils/notify-event-listeners.js";
import { BaseSubscribable } from "../../subscribable/subscribable.js";
import { isMessageNotSentError } from "../../types/error.js";
import { EMPTY_QUEUE_ITEMS } from "../queue/queue-item.js";
import { isAttachmentComplete, isCreateAttachment } from "../../types/attachment.js";
import { AttachmentAddOperations, drainAttachmentAdd } from "../utils/attachment-add-operations.js";
import { AttachmentSendOperations } from "../utils/attachment-send-operations.js";
//#region src/runtime/base/base-composer-runtime-core.ts
var BaseComposerRuntimeCore = class extends BaseSubscribable {
	isEditing = true;
	enrichWithComposerMetadata(message, composerMetadata) {
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
	get attachmentAccept() {
		return this.getAttachmentAdapter()?.accept ?? "*";
	}
	_attachments = [];
	get attachments() {
		return this._attachments;
	}
	setAttachments(value) {
		this._attachments = value;
		this._notifySubscribers();
	}
	get isEmpty() {
		return !this.text.trim() && !this.attachments.length;
	}
	_text = "";
	get text() {
		return this._text;
	}
	_role = "user";
	get role() {
		return this._role;
	}
	_runConfig = {};
	get runConfig() {
		return this._runConfig;
	}
	_quote = void 0;
	get quote() {
		return this._quote;
	}
	setQuote(quote) {
		if (this._quote === quote) return;
		this._quote = quote;
		this._notifySubscribers();
	}
	setText(value) {
		if (this._text === value) return;
		this._text = value;
		this._rebaseDictation(value);
		this._notifySubscribers();
	}
	_rebaseDictation(value) {
		if (!this._dictation) return;
		this._dictationBaseText = value;
		this._currentInterimText = "";
		const { status, inputDisabled } = this._dictation;
		this._dictation = inputDisabled ? {
			status,
			inputDisabled
		} : { status };
	}
	setRole(role) {
		if (this._role === role) return;
		this._role = role;
		this._notifySubscribers();
	}
	setRunConfig(runConfig) {
		if (this._runConfig === runConfig) return;
		this._runConfig = runConfig;
		this._notifySubscribers();
	}
	_submission;
	_submissionSend;
	_inTransit = [];
	_inTransitSubmissions = [];
	_sendGeneration = 0;
	_attachmentAddOperations = new AttachmentAddOperations();
	_attachmentSends = new AttachmentSendOperations();
	get submission() {
		return this._submission;
	}
	get inTransit() {
		return this._inTransitSubmissions;
	}
	/** Whether a send is still being prepared, which holds the composer. */
	get isSubmitting() {
		return this._submission !== void 0;
	}
	/** Whether a send takes the draft with it, leaving the composer free. */
	get detachesDraftOnSend() {
		return true;
	}
	/**
	* The ids of the thread's messages of a role, or undefined when this
	* composer's sends do not render in the thread. A dispatched submission
	* stays in transit until a message of its role that was not there at
	* dispatch shows up.
	*/
	threadMessageIds(_role) {}
	/**
	* Releases the messages in transit that the thread now shows. Each new
	* message stands in for the oldest send still waiting for one, and only
	* once, so sends made in quick succession hand over in order.
	*/
	settleInTransit() {
		if (this._inTransit.length === 0) return;
		const claimed = /* @__PURE__ */ new Set();
		const pending = this._inTransit.filter(({ submission, known }) => {
			const shown = this.threadMessageIds(submission.role)?.find((id) => !known.has(id) && !claimed.has(id));
			if (shown === void 0) return true;
			claimed.add(shown);
			return false;
		});
		if (pending.length === this._inTransit.length) return;
		this._setInTransit(pending.map((entry) => ({
			...entry,
			known: /* @__PURE__ */ new Set([...entry.known, ...claimed])
		})));
		this._notifySubscribers();
	}
	_setInTransit(entries) {
		this._inTransit = entries;
		this._inTransitSubmissions = entries.map((entry) => entry.submission);
	}
	_leaveTransit(submission) {
		const remaining = this._inTransit.filter((entry) => entry.submission !== submission);
		if (remaining.length === this._inTransit.length) return false;
		this._setInTransit(remaining);
		return true;
	}
	_cancelAttachmentAdd(attachmentId) {
		this._attachmentAddOperations.cancel(attachmentId);
	}
	_cancelAllAttachmentAdds() {
		this._attachmentAddOperations.cancelAll();
	}
	_emptyTextAndAttachments() {
		this._attachments = [];
		this._text = "";
		this._rebaseDictation("");
		this._notifySubscribers();
	}
	async _onClearAttachments() {
		const adapter = this.getAttachmentAdapter();
		if (adapter) {
			const pending = this._attachments.filter((a) => !isAttachmentComplete(a));
			await Promise.all(pending.map(async (a) => adapter.remove(a)));
		}
	}
	async reset() {
		this._cancelAllAttachmentAdds();
		this._sendGeneration++;
		const discarded = this._discardSubmission();
		if (this._attachments.length === 0 && this._text === "" && this._role === "user" && Object.keys(this._runConfig).length === 0 && this._quote === void 0) {
			await discarded;
			return;
		}
		this._role = "user";
		this._runConfig = {};
		this._quote = void 0;
		const task = this._onClearAttachments();
		this._emptyTextAndAttachments();
		await Promise.all([task, discarded]);
	}
	async clearAttachments() {
		this._cancelAllAttachmentAdds();
		if (this.isSubmitting) for (const attachment of this._attachments) this._attachmentSends.markRemoved(attachment);
		const task = this._onClearAttachments();
		this.setAttachments([]);
		await task;
	}
	async send(options) {
		if (!this.canSend || this.isSubmitting) return;
		if (this._dictationSession) {
			const sessionId = this._activeDictationSessionId;
			try {
				this._dictationSession.cancel();
			} catch (error) {
				console.error("[assistant-ui] Dictation session cancel threw", error);
			} finally {
				this._cleanupDictation({ sessionId });
			}
		}
		const attachments = this.attachments.filter((attachment) => !this._attachmentSends.isRemoved(attachment));
		if (!this.text.trim() && attachments.length === 0) return;
		const draft = {
			id: generateId(),
			role: this.role,
			text: this.text,
			quote: this._quote,
			attachments
		};
		const context = {
			options,
			runConfig: this.runConfig
		};
		const complete = attachments.filter(isAttachmentComplete);
		const ready = complete.length === attachments.length;
		if (!ready) {
			this._submission = draft;
			this._submissionSend = {
				...context,
				controller: new AbortController()
			};
		}
		if (this.detachesDraftOnSend) {
			const detached = new Set(attachments);
			this._attachments = this._attachments.filter((a) => !detached.has(a));
			this._text = "";
			this._rebaseDictation("");
			this._quote = void 0;
		}
		const generation = ++this._sendGeneration;
		this._notifySubscribers();
		if (ready) {
			this._dispatch(generation, draft, complete, context, false);
			return;
		}
		await this._prepareSubmission(generation);
	}
	async _prepareSubmission(generation) {
		const adapter = this.getAttachmentAdapter();
		const uploads = (this._submission?.attachments ?? []).flatMap((attachment) => {
			const upload = this._attachmentAddOperations.whenSendable(attachment.id);
			return upload ? [upload] : [];
		});
		if (uploads.length > 0) {
			await Promise.all(uploads);
			if (generation !== this._sendGeneration) return;
			this._refreshSubmissionAttachments();
		}
		const submission = this._submission;
		const context = this._submissionSend;
		if (!submission || !context) return;
		const sent = submission.attachments.filter((attachment) => !this._attachmentSends.isRemoved(attachment));
		for (const attachment of sent) this._cancelAttachmentAdd(attachment.id);
		const settled = await Promise.allSettled(sent.map((attachment) => this._attachmentSends.send(attachment, adapter, context.controller.signal)));
		if (generation !== this._sendGeneration) return;
		const rejection = settled.find((result) => result.status === "rejected");
		if (rejection) {
			this._returnSubmissionToDraft(sent, settled, rejection.reason);
			return;
		}
		const finalAttachments = settled.flatMap((result, index) => this._attachmentSends.isRemoved(sent[index]) || result.status === "rejected" ? [] : [result.value]);
		this._dispatch(generation, submission, finalAttachments, context, true);
	}
	_dispatch(generation, draft, attachments, context, isSubmission) {
		const message = {
			createdAt: /* @__PURE__ */ new Date(),
			role: draft.role,
			content: draft.text ? [{
				type: "text",
				text: draft.text
			}] : [],
			attachments,
			runConfig: context.runConfig,
			metadata: { custom: { ...draft.quote ? { quote: draft.quote } : {} } }
		};
		const sent = {
			...draft,
			attachments
		};
		const queued = this.queue.length;
		if (isSubmission) {
			this._submission = void 0;
			this._submissionSend = void 0;
			if (!this.detachesDraftOnSend) {
				const delivered = new Map(attachments.map((attachment) => [attachment.id, attachment]));
				this._attachments = this._attachments.map((attachment) => delivered.get(attachment.id) ?? attachment);
			}
			const known = this.threadMessageIds(draft.role);
			if (known) this._setInTransit([...this._inTransit, {
				submission: sent,
				known: new Set(known)
			}]);
		}
		let sendTask;
		try {
			sendTask = this.handleSend(message, context.options);
		} catch (error) {
			console.error("[assistant-ui] Failed to send the message", error);
			this._leaveTransit(sent);
			if (generation === this._sendGeneration) this._returnToDraft(sent);
			else this._notifySubscribers();
			return;
		}
		if (sendTask) sendTask.catch((error) => {
			const wasInTransit = this._leaveTransit(sent);
			if (generation === this._sendGeneration && isMessageNotSentError(error)) this._returnToDraft(sent);
			else if (wasInTransit) this._notifySubscribers();
		});
		this._notifyEventSubscribers("send", {
			chars: draft.text.length,
			attachments: attachments.length
		});
		if (!isSubmission) return;
		if (this.queue.length > queued) this._leaveTransit(sent);
		this._notifySubscribers();
		this.settleInTransit();
	}
	_refreshSubmissionAttachments() {
		const submission = this._submission;
		if (!submission) return;
		const attachments = submission.attachments.filter((attachment) => !this._attachmentSends.isRemoved(attachment));
		if (attachments.length === submission.attachments.length) return;
		this._submission = {
			...submission,
			attachments
		};
	}
	_returnSubmissionToDraft(sent, settled, reason) {
		const submission = this._submission;
		if (!submission) return;
		const failures = /* @__PURE__ */ new Map();
		settled.forEach((result, index) => {
			if (result.status === "rejected") failures.set(sent[index].id, result.reason);
		});
		const attachments = submission.attachments.map((attachment) => {
			if (!failures.has(attachment.id) || isAttachmentComplete(attachment)) return attachment;
			const failure = failures.get(attachment.id);
			return this._attachmentSends.transfer(attachment, {
				...attachment,
				status: {
					type: "incomplete",
					reason: "error",
					message: failure instanceof Error ? failure.message : String(failure)
				}
			});
		});
		this._endSubmission();
		this._returnToDraft({
			...submission,
			attachments
		});
		console.error("[assistant-ui] Failed to send attachments", reason);
	}
	/** Ends the send being prepared, so nothing it started can dispatch it. */
	_endSubmission() {
		this._sendGeneration++;
		this._submission = void 0;
		this._submissionSend = void 0;
	}
	/** Drops the send being prepared without returning it to the draft, for a thread runtime disposed for good. */
	__internal_dispose() {
		this._cancelAllAttachmentAdds();
		if (!this._submission) return;
		this._submissionSend?.controller.abort();
		this._endSubmission();
		this._notifySubscribers();
	}
	/**
	* Stops the submission and takes its content back into the draft, merging it
	* ahead of anything written since, so a send is never dropped.
	*/
	cancelSubmission() {
		const submission = this._submission;
		if (!submission) return;
		this._submissionSend?.controller.abort();
		this._endSubmission();
		this._returnToDraft(submission);
	}
	/**
	* Takes a send's content back into the draft, ahead of anything written
	* since. A composer that kept its draft only takes back the state the
	* attachments came back in, such as the reason one failed.
	*/
	_returnToDraft(submission) {
		if (this.detachesDraftOnSend) {
			const kept = submission.attachments.filter((attachment) => !this._attachmentSends.isRemoved(attachment));
			this._attachments = [...kept, ...this._attachments];
			const text = [submission.text, this._text].filter(Boolean).join("\n");
			this._text = text;
			this._rebaseDictation(text);
			this._quote = this._quote ?? submission.quote;
		} else {
			const returned = new Map(submission.attachments.map((attachment) => [attachment.id, attachment]));
			this._attachments = this._attachments.map((attachment) => returned.get(attachment.id) ?? attachment);
		}
		this._notifySubscribers();
	}
	async _discardSubmission() {
		const submission = this._submission;
		if (!submission) return;
		this._submissionSend?.controller.abort();
		this._endSubmission();
		this._notifySubscribers();
		const adapter = this.getAttachmentAdapter();
		if (!adapter) return;
		const drafted = new Set(this._attachments.map((attachment) => attachment.id));
		await Promise.all(submission.attachments.filter((attachment) => !isAttachmentComplete(attachment) && !drafted.has(attachment.id)).map(async (attachment) => adapter.remove(attachment)));
	}
	/**
	* Take a message back into the composer when it has nowhere else to live:
	* a send the runtime never dispatched, or a message a cancelled run is
	* removing from the thread. Reports whether the composer accepted it, so a
	* caller that is also removing the message can keep it instead of dropping
	* it. Refused, and left untouched, while the composer holds anything of its
	* own.
	*/
	restoreDraft(draft) {
		if (this._text.trim() || this._quote !== void 0 || this._attachments.length > 0) return false;
		this._text = draft.text;
		this._rebaseDictation(draft.text);
		this._quote = draft.quote;
		this._attachments = draft.attachments ?? [];
		this._notifySubscribers();
		return true;
	}
	/**
	* Inverse of `restoreDraft`: clears the composer while it still holds
	* exactly the given draft. A draft the user has edited since is left
	* untouched.
	*/
	retractDraft(draft) {
		const attachmentsUntouched = draft.attachments !== void 0 ? this._attachments === draft.attachments : this._attachments.length === 0;
		if (this._text !== draft.text || this._quote !== draft.quote || !attachmentsUntouched) return;
		this._text = "";
		this._rebaseDictation("");
		this._quote = void 0;
		this._attachments = [];
		this._notifySubscribers();
	}
	cancel() {
		if (this.isSubmitting && !this.detachesDraftOnSend) {
			this._submissionSend?.controller.abort();
			this._endSubmission();
			this._notifySubscribers();
		}
		this.handleCancel();
	}
	get queue() {
		return EMPTY_QUEUE_ITEMS;
	}
	moveQueueItem(_queueItemId, _placement) {}
	editQueueItem(_queueItemId, _message) {}
	removeQueueItem(_queueItemId) {}
	async addAttachment(fileOrAttachment) {
		if (isCreateAttachment(fileOrAttachment)) {
			const adapter = this.getAttachmentAdapter();
			if (adapter && !fileMatchesAccept({
				name: fileOrAttachment.name,
				type: fileOrAttachment.contentType ?? ""
			}, adapter.accept)) {
				const message = `File type ${fileOrAttachment.contentType || "unknown"} is not accepted. Accepted types: ${adapter.accept}`;
				const err = new Error(message);
				this._safeEmitAttachmentAddError("not-accepted", message, void 0, err, fileOrAttachment.contentType);
				throw err;
			}
			const a = {
				id: fileOrAttachment.id ?? generateId(),
				type: fileOrAttachment.type ?? "document",
				name: fileOrAttachment.name,
				contentType: fileOrAttachment.contentType,
				content: fileOrAttachment.content,
				status: { type: "complete" }
			};
			this._attachments = [...this._attachments, a];
			this._notifySubscribers();
			this._notifyEventSubscribers("attachmentAdd", { ...a.contentType ? { contentType: a.contentType } : void 0 });
			return;
		}
		const adapter = this.getAttachmentAdapter();
		if (!adapter) {
			const message = "Attachments are not supported";
			const err = /* @__PURE__ */ new Error(message);
			this._safeEmitAttachmentAddError("no-adapter", message, void 0, err, fileOrAttachment.type);
			throw err;
		}
		if (!fileMatchesAccept({
			name: fileOrAttachment.name,
			type: fileOrAttachment.type
		}, adapter.accept)) {
			const message = `File type ${fileOrAttachment.type || "unknown"} is not accepted. Accepted types: ${adapter.accept}`;
			const err = new Error(message);
			this._safeEmitAttachmentAddError("not-accepted", message, void 0, err, fileOrAttachment.type);
			throw err;
		}
		const operation = this._attachmentAddOperations.start();
		const upsertAttachment = (a) => {
			if (!this._attachmentAddOperations.accept(operation, a)) return false;
			const submission = this._submission;
			const submitted = submission?.attachments.some((attachment) => attachment.id === a.id) ?? false;
			if (submission && submitted) this._submission = {
				...submission,
				attachments: submission.attachments.map((attachment) => attachment.id === a.id ? this._attachmentSends.transfer(attachment, a) : attachment)
			};
			const idx = this._attachments.findIndex((attachment) => attachment.id === a.id);
			if (idx !== -1) this._attachments = [
				...this._attachments.slice(0, idx),
				a,
				...this._attachments.slice(idx + 1)
			];
			else if (!submitted) this._attachments = [...this._attachments, a];
			this._notifySubscribers();
			return true;
		};
		let lastAttachment;
		try {
			await drainAttachmentAdd(adapter.add({ file: fileOrAttachment }), (attachment) => {
				lastAttachment = attachment;
				return upsertAttachment(attachment);
			});
		} catch (e) {
			if (this._attachmentAddOperations.isCancelled(operation)) return;
			if (lastAttachment) upsertAttachment({
				...lastAttachment,
				status: {
					type: "incomplete",
					reason: "error",
					message: e instanceof Error ? e.message : String(e)
				}
			});
			this._safeEmitAttachmentAddError("adapter-error", e instanceof Error ? e.message : String(e), lastAttachment?.id, e instanceof Error ? e : void 0, lastAttachment?.contentType || fileOrAttachment.type);
			throw e;
		} finally {
			this._attachmentAddOperations.finish(operation);
		}
		if (this._attachmentAddOperations.isCancelled(operation)) return;
		if (lastAttachment?.status.type === "incomplete" && lastAttachment.status.reason === "error") this._safeEmitAttachmentAddError("adapter-error", lastAttachment.status.message ?? "Attachment upload did not complete successfully.", lastAttachment.id, void 0, lastAttachment.contentType || fileOrAttachment.type);
		else this._notifyEventSubscribers("attachmentAdd", { ...lastAttachment?.contentType ? { contentType: lastAttachment.contentType } : fileOrAttachment.type ? { contentType: fileOrAttachment.type } : void 0 });
	}
	_safeEmitAttachmentAddError(reason, message, attachmentId, error, contentType) {
		try {
			this._notifyEventSubscribers("attachmentAddError", {
				reason,
				message,
				...attachmentId !== void 0 && { attachmentId },
				...error !== void 0 && { error },
				...contentType ? { contentType } : void 0
			});
		} catch (subscriberError) {
			console.error("[assistant-ui] attachmentAddError subscriber threw:", subscriberError);
		}
	}
	async removeAttachment(attachmentId) {
		const index = this._attachments.findIndex((a) => a.id === attachmentId);
		if (index === -1) {
			await this._removeSubmittedAttachment(attachmentId);
			return;
		}
		const attachment = this._attachments[index];
		this._cancelAttachmentAdd(attachmentId);
		this._attachmentSends.markRemoved(attachment);
		if (!isAttachmentComplete(attachment)) {
			const adapter = this.getAttachmentAdapter();
			if (!adapter) throw new Error("Attachments are not supported");
			try {
				await adapter.remove(attachment);
			} catch (error) {
				const message = error instanceof Error ? error.message : String(error);
				this._attachments = this._attachments.map((candidate) => candidate.id === attachmentId && !isAttachmentComplete(candidate) ? this._attachmentSends.transfer(candidate, {
					...candidate,
					status: {
						type: "incomplete",
						reason: "error",
						message
					}
				}) : candidate);
				this._notifySubscribers();
				throw error;
			}
		}
		this._attachments = this._attachments.filter((a) => a.id !== attachmentId);
		this._notifySubscribers();
	}
	/**
	* A submission is not delivered yet, so an attachment can still be taken out
	* of it, which the draft no longer holds once the send detached it.
	*/
	async _removeSubmittedAttachment(attachmentId) {
		const submitted = this._submission?.attachments.find((a) => a.id === attachmentId);
		if (!submitted) throw new Error("Attachment not found");
		this._cancelAttachmentAdd(attachmentId);
		this._attachmentSends.markRemoved(submitted);
		if (!isAttachmentComplete(submitted)) {
			const adapter = this.getAttachmentAdapter();
			if (!adapter) throw new Error("Attachments are not supported");
			try {
				await adapter.remove(submitted);
			} catch (error) {
				this._failSubmittedRemoval(attachmentId, error);
				throw error;
			}
		}
		const submission = this._submission;
		if (!submission) return;
		this._submission = {
			...submission,
			attachments: submission.attachments.filter((a) => a.id !== attachmentId)
		};
		this._notifySubscribers();
	}
	/**
	* An attachment whose removal failed stays out of the message it was taken
	* from and shows why, so the removal can be tried again.
	*/
	_failSubmittedRemoval(attachmentId, error) {
		const submission = this._submission;
		if (!submission) return;
		const message = error instanceof Error ? error.message : String(error);
		this._submission = {
			...submission,
			attachments: submission.attachments.map((attachment) => {
				if (attachment.id !== attachmentId || isAttachmentComplete(attachment)) return attachment;
				const failed = this._attachmentSends.transfer(attachment, {
					...attachment,
					status: {
						type: "incomplete",
						reason: "error",
						message
					}
				});
				this._attachmentSends.markRemoved(failed);
				return failed;
			})
		};
		this._notifySubscribers();
	}
	_dictation;
	_dictationSession;
	_dictationUnsubscribes = [];
	_dictationBaseText = "";
	_currentInterimText = "";
	_dictationSessionIdCounter = 0;
	_activeDictationSessionId;
	_isCleaningDictation = false;
	get dictation() {
		return this._dictation;
	}
	_isActiveSession(sessionId, session) {
		return this._activeDictationSessionId === sessionId && this._dictationSession === session;
	}
	startDictation() {
		const adapter = this.getDictationAdapter();
		if (!adapter) throw new Error("Dictation adapter not configured");
		const isReplacing = this._dictationSession !== void 0;
		if (this._dictationSession) {
			const oldSession = this._dictationSession;
			this._cleanupDictation({ notify: false });
			this._stopDictationSession(oldSession);
		}
		const inputDisabled = adapter.disableInputDuringDictation ?? false;
		this._dictationBaseText = this._text;
		this._currentInterimText = "";
		let session;
		try {
			session = adapter.listen();
		} catch (error) {
			if (isReplacing) try {
				this._notifySubscribers();
			} catch (notifyError) {
				console.error("[assistant-ui] Dictation replacement rollback notification threw", notifyError);
			}
			throw error;
		}
		this._dictationSession = session;
		const sessionId = ++this._dictationSessionIdCounter;
		this._activeDictationSessionId = sessionId;
		this._dictation = {
			status: session.status,
			inputDisabled
		};
		try {
			this._notifySubscribers();
		} catch (notifyError) {
			console.error("[assistant-ui] Dictation start notification threw", notifyError);
		}
		if (!this._isActiveSession(sessionId, session)) return;
		const setupUnsubscribes = [];
		const releaseSetup = () => {
			for (const unsubscribe of setupUnsubscribes.splice(0)) try {
				unsubscribe();
			} catch (cleanupError) {
				console.error("[assistant-ui] Dictation cleanup threw", cleanupError);
			}
		};
		const keepUnsubscribe = (unsubscribe) => {
			setupUnsubscribes.push(unsubscribe);
			if (this._isActiveSession(sessionId, session)) return true;
			releaseSetup();
			return false;
		};
		try {
			if (!keepUnsubscribe(session.onSpeech((result) => {
				if (!this._isActiveSession(sessionId, session)) return;
				const isFinal = result.isFinal !== false;
				const separator = this._dictationBaseText && !this._dictationBaseText.endsWith(" ") && result.transcript ? " " : "";
				if (isFinal) {
					this._dictationBaseText = this._dictationBaseText + separator + result.transcript;
					this._currentInterimText = "";
					this._text = this._dictationBaseText;
					if (this._dictation) {
						const { transcript: _, ...rest } = this._dictation;
						this._dictation = rest;
					}
					this._notifySubscribers();
				} else {
					this._currentInterimText = separator + result.transcript;
					this._text = this._dictationBaseText + this._currentInterimText;
					if (this._dictation) this._dictation = {
						...this._dictation,
						transcript: result.transcript
					};
					this._notifySubscribers();
				}
			}))) return;
			if (!keepUnsubscribe(session.onSpeechStart(() => {
				if (!this._isActiveSession(sessionId, session)) return;
				this._dictation = {
					status: { type: "running" },
					inputDisabled,
					...this._dictation?.transcript && { transcript: this._dictation.transcript }
				};
				this._notifySubscribers();
			}))) return;
			if (!keepUnsubscribe(session.onSpeechEnd(() => {
				this._cleanupDictation({ sessionId });
			}))) return;
			const statusInterval = setInterval(() => {
				if (!this._isActiveSession(sessionId, session)) return;
				if (session.status.type === "ended") this._cleanupDictation({ sessionId });
			}, 100);
			if (!keepUnsubscribe(() => clearInterval(statusInterval))) return;
			this._dictationUnsubscribes.push(...setupUnsubscribes.splice(0));
		} catch (error) {
			releaseSetup();
			if (this._isActiveSession(sessionId, session)) try {
				session.cancel();
			} catch (cancelError) {
				console.error("[assistant-ui] Dictation session cancel threw", cancelError);
			} finally {
				this._cleanupDictation({ sessionId });
			}
			throw error;
		}
	}
	stopDictation() {
		if (!this._dictationSession) return;
		const session = this._dictationSession;
		const sessionId = this._activeDictationSessionId;
		const cleanup = () => this._cleanupDictation({ sessionId });
		this._stopDictationSession(session, cleanup);
	}
	_stopDictationSession(session, onSettled = () => {}) {
		let task;
		try {
			task = session.stop();
		} catch (error) {
			console.error("[assistant-ui] Dictation session stop threw", error);
			onSettled();
			return;
		}
		task.then(onSettled, (error) => {
			console.error("[assistant-ui] Dictation session stop rejected", error);
			onSettled();
		});
	}
	_cleanupDictation(options) {
		if (options?.sessionId !== void 0 && options.sessionId !== this._activeDictationSessionId || this._isCleaningDictation) return;
		this._isCleaningDictation = true;
		const runCleanup = (cleanup) => {
			try {
				cleanup();
			} catch (error) {
				console.error("[assistant-ui] Dictation cleanup threw", error);
			}
		};
		try {
			const unsubscribes = this._dictationUnsubscribes;
			this._dictationUnsubscribes = [];
			this._dictationSession = void 0;
			this._activeDictationSessionId = void 0;
			this._dictation = void 0;
			this._dictationBaseText = "";
			this._currentInterimText = "";
			for (const unsubscribe of unsubscribes) runCleanup(unsubscribe);
			if (options?.notify !== false) runCleanup(() => this._notifySubscribers());
		} finally {
			this._isCleaningDictation = false;
		}
	}
	_eventSubscribers = /* @__PURE__ */ new Map();
	_notifyEventSubscribers(event, payload) {
		const subscribers = this._eventSubscribers.get(event);
		if (!subscribers) return;
		notifyEventListeners(subscribers, payload, `Composer runtime "${event}"`);
	}
	unstable_on(event, callback) {
		const wrapped = callback;
		let subscribers = this._eventSubscribers.get(event);
		if (!subscribers) {
			subscribers = /* @__PURE__ */ new Set();
			this._eventSubscribers.set(event, subscribers);
		}
		subscribers.add(wrapped);
		return () => {
			this._eventSubscribers.get(event)?.delete(wrapped);
		};
	}
};
//#endregion
export { BaseComposerRuntimeCore };
