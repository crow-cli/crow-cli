import { generateId } from "../../utils/id.js";
import { fileMatchesAccept } from "../../adapters/attachment.js";
import { getThreadMessageText } from "../../utils/text.js";
import { createToolInteraction } from "../../runtime/utils/tool-interactions.js";
import { toMessagePartStatus } from "../../utils/normalizePartStatus.js";
import { getMessagePartKeys } from "../../utils/getMessagePartKeys.js";
import { resolveToolApprovalResponse } from "../../runtime/utils/resolveToolApprovalResponse.js";
import { isAttachmentComplete, isCreateAttachment } from "../../types/attachment.js";
import { AttachmentAddOperations, drainAttachmentAdd } from "../../runtime/utils/attachment-add-operations.js";
import { AttachmentSendOperations } from "../../runtime/utils/attachment-send-operations.js";
import { ThreadMessageClient } from "./thread-message-client.js";
import { submissionThreadMessage } from "./submission-message.js";
import { ThreadSuggestions } from "./suggestions.js";
import { TaskClient, createTaskDeriver, getTaskKey } from "./thread-tasks.js";
import { ModelContext } from "./model-context-client.js";
import { DataRenderers } from "../../react/client/DataRenderers.js";
import { Tools } from "../../react/client/Tools.js";
import { SingleThreadList } from "./single-thread-list.js";
import { Derived, attachTransformScopes, useClientLookup, useClientResource } from "@assistant-ui/store/client";
import { ToolResponse } from "assistant-stream";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useEffect, useRef, useState } from "@assistant-ui/tap/react-shim";
import { resource, withKey } from "@assistant-ui/tap";
import { useAssistantClientDestroySignal } from "@assistant-ui/store/internal";
//#region src/store/clients/external-thread.ts
const EMPTY_QUEUE_ITEMS = [];
const EMPTY_BRANCH_IDS = [];
const EMPTY_SUGGESTIONS = [];
const COMPLETE_STATUS = Object.freeze({ type: "complete" });
const derivePartStatus = (message, partIndex, part) => {
	if (!message.status) return COMPLETE_STATUS;
	return toMessagePartStatus(message, partIndex, part);
};
const useMessageClient = (t0) => {
	const $ = c(74);
	const { message, index, isLast, parentId, onEdit, onReload, queue, branches, onRespondToToolApproval, unstable_onRecordToolInteraction, onAddToolResult, onResumeToolCall, attachmentAdapter, submittedFeedback, onSubmitFeedback, speech, onSpeak, onStopSpeaking } = t0;
	const [isCopied, setIsCopied] = useState(false);
	const [isHovering, setIsHovering] = useState(false);
	let t1;
	let t2;
	if ($[0] !== message || $[1] !== onAddToolResult || $[2] !== onRespondToToolApproval || $[3] !== onResumeToolCall || $[4] !== unstable_onRecordToolInteraction) {
		const partKeys = getMessagePartKeys(message.content);
		t1 = useClientLookup;
		t2 = message.content.map((part, idx) => withKey(partKeys[idx], PartResource({
			part,
			status: derivePartStatus(message, idx, part),
			messageId: message.id,
			onRespondToToolApproval,
			unstable_onRecordToolInteraction,
			onAddToolResult,
			onResumeToolCall
		})));
		$[0] = message;
		$[1] = onAddToolResult;
		$[2] = onRespondToToolApproval;
		$[3] = onResumeToolCall;
		$[4] = unstable_onRecordToolInteraction;
		$[5] = t1;
		$[6] = t2;
	} else {
		t1 = $[5];
		t2 = $[6];
	}
	const partClients = t1(t2);
	let t3;
	if ($[7] !== message.attachments) {
		t3 = message.attachments ?? [];
		$[7] = message.attachments;
		$[8] = t3;
	} else t3 = $[8];
	let t4;
	if ($[9] !== t3) {
		t4 = t3.map(_temp2);
		$[9] = t3;
		$[10] = t4;
	} else t4 = $[10];
	const attachmentClients = useClientLookup(t4);
	let t5;
	if ($[11] !== onEdit) {
		t5 = () => {
			if (!onEdit) throw new Error("Runtime does not support editing.");
		};
		$[11] = onEdit;
		$[12] = t5;
	} else t5 = $[12];
	const handleBeginEdit = t5;
	let t6;
	if ($[13] !== message.id || $[14] !== onEdit || $[15] !== parentId) {
		t6 = (msg) => {
			if (!onEdit) throw new Error("Runtime does not support editing.");
			onEdit({
				...msg,
				parentId,
				sourceId: message.id
			});
		};
		$[13] = message.id;
		$[14] = onEdit;
		$[15] = parentId;
		$[16] = t6;
	} else t6 = $[16];
	const handleSendEdit = t6;
	let t7;
	if ($[17] !== attachmentAdapter || $[18] !== handleBeginEdit || $[19] !== handleSendEdit || $[20] !== message || $[21] !== queue) {
		t7 = ComposerClientResource({
			type: "edit",
			canCancel: true,
			onBeginEdit: handleBeginEdit,
			onSend: handleSendEdit,
			message,
			queue,
			attachmentAdapter
		});
		$[17] = attachmentAdapter;
		$[18] = handleBeginEdit;
		$[19] = handleSendEdit;
		$[20] = message;
		$[21] = queue;
		$[22] = t7;
	} else t7 = $[22];
	const composerClient = useClientResource(t7);
	let branchIds;
	let t8;
	if ($[23] !== branches || $[24] !== message.id) {
		branchIds = branches?.getBranches(message.id) ?? EMPTY_BRANCH_IDS;
		t8 = branchIds.indexOf(message.id);
		$[23] = branches;
		$[24] = message.id;
		$[25] = branchIds;
		$[26] = t8;
	} else {
		branchIds = $[25];
		t8 = $[26];
	}
	const branchIndex = t8;
	const branchNumber = branchIndex === -1 ? 1 : branchIndex + 1;
	const branchCount = branchIndex === -1 ? 1 : branchIds.length;
	let t9;
	if ($[27] !== message || $[28] !== submittedFeedback) {
		t9 = submittedFeedback && message.role === "assistant" ? {
			...message,
			metadata: {
				...message.metadata,
				submittedFeedback
			}
		} : message;
		$[27] = message;
		$[28] = submittedFeedback;
		$[29] = t9;
	} else t9 = $[29];
	const messageWithFeedback = t9;
	let t10;
	if ($[30] !== message.attachments) {
		t10 = message.attachments ?? [];
		$[30] = message.attachments;
		$[31] = t10;
	} else t10 = $[31];
	let t11;
	if ($[32] !== branchCount || $[33] !== branchNumber || $[34] !== composerClient.state || $[35] !== index || $[36] !== isCopied || $[37] !== isHovering || $[38] !== isLast || $[39] !== messageWithFeedback || $[40] !== parentId || $[41] !== partClients.state || $[42] !== speech || $[43] !== t10) {
		t11 = {
			...messageWithFeedback,
			attachments: t10,
			parentId,
			isLast,
			branchNumber,
			branchCount,
			speech,
			parts: partClients.state,
			isCopied,
			isHovering,
			index,
			composer: composerClient.state
		};
		$[32] = branchCount;
		$[33] = branchNumber;
		$[34] = composerClient.state;
		$[35] = index;
		$[36] = isCopied;
		$[37] = isHovering;
		$[38] = isLast;
		$[39] = messageWithFeedback;
		$[40] = parentId;
		$[41] = partClients.state;
		$[42] = speech;
		$[43] = t10;
		$[44] = t11;
	} else t11 = $[44];
	const state = t11;
	let t12;
	if ($[45] !== state) {
		t12 = () => state;
		$[45] = state;
		$[46] = t12;
	} else t12 = $[46];
	let t13;
	if ($[47] !== composerClient.methods) {
		t13 = () => composerClient.methods;
		$[47] = composerClient.methods;
		$[48] = t13;
	} else t13 = $[48];
	let t14;
	if ($[49] !== onReload) {
		t14 = () => {
			onReload?.();
		};
		$[49] = onReload;
		$[50] = t14;
	} else t14 = $[50];
	let t15;
	if ($[51] !== branchIds || $[52] !== branchIndex || $[53] !== branches || $[54] !== message.id) {
		t15 = (t16) => {
			const { position, branchId } = t16;
			if (!branches) return;
			const target = branchId ?? (branchIndex === -1 ? void 0 : position === "previous" ? branchIds[branchIndex - 1] : position === "next" ? branchIds[branchIndex + 1] : void 0);
			if (target !== void 0 && target !== message.id) branches.switchToBranch(target);
		};
		$[51] = branchIds;
		$[52] = branchIndex;
		$[53] = branches;
		$[54] = message.id;
		$[55] = t15;
	} else t15 = $[55];
	let t16;
	if ($[56] !== message) {
		t16 = () => getThreadMessageText(message);
		$[56] = message;
		$[57] = t16;
	} else t16 = $[57];
	let t17;
	if ($[58] !== partClients || $[59] !== state) {
		t17 = (selector) => {
			if ("index" in selector) return partClients.get(selector);
			const partIndex = state.parts.findIndex((p) => p.type === "tool-call" && p.toolCallId === selector.toolCallId);
			return partClients.get({ index: partIndex });
		};
		$[58] = partClients;
		$[59] = state;
		$[60] = t17;
	} else t17 = $[60];
	let t18;
	if ($[61] !== attachmentClients) {
		t18 = (selector_0) => {
			if ("id" in selector_0) return attachmentClients.get({ key: selector_0.id });
			return attachmentClients.get(selector_0);
		};
		$[61] = attachmentClients;
		$[62] = t18;
	} else t18 = $[62];
	let t19;
	if ($[63] !== onSpeak || $[64] !== onStopSpeaking || $[65] !== onSubmitFeedback || $[66] !== t12 || $[67] !== t13 || $[68] !== t14 || $[69] !== t15 || $[70] !== t16 || $[71] !== t17 || $[72] !== t18) {
		t19 = {
			getState: t12,
			composer: t13,
			delete: _temp3,
			reload: t14,
			speak: onSpeak,
			stopSpeaking: onStopSpeaking,
			submitFeedback: onSubmitFeedback,
			switchToBranch: t15,
			getCopyText: t16,
			part: t17,
			attachment: t18,
			setIsCopied,
			setIsHovering
		};
		$[63] = onSpeak;
		$[64] = onStopSpeaking;
		$[65] = onSubmitFeedback;
		$[66] = t12;
		$[67] = t13;
		$[68] = t14;
		$[69] = t15;
		$[70] = t16;
		$[71] = t17;
		$[72] = t18;
		$[73] = t19;
	} else t19 = $[73];
	return t19;
};
const MessageClient = resource(useMessageClient);
const usePartResource = (t0) => {
	const $ = c(27);
	const { part, status, messageId, onRespondToToolApproval, unstable_onRecordToolInteraction, onAddToolResult, onResumeToolCall } = t0;
	const t1 = status;
	let t2;
	if ($[0] !== part || $[1] !== t1) {
		t2 = {
			...part,
			status: t1
		};
		$[0] = part;
		$[1] = t1;
		$[2] = t2;
	} else t2 = $[2];
	const state = t2;
	let t3;
	if ($[3] !== state) {
		t3 = () => state;
		$[3] = state;
		$[4] = t3;
	} else t3 = $[4];
	let t4;
	if ($[5] !== messageId || $[6] !== onAddToolResult || $[7] !== part) {
		t4 = (result) => {
			if (!onAddToolResult) throw new Error("Runtime does not support tool results (onAddToolResult is not set).");
			if (part.type !== "tool-call") throw new Error("Tried to add tool result on non-tool message part");
			const response = ToolResponse.toResponse(result);
			onAddToolResult({
				messageId,
				toolName: part.toolName,
				toolCallId: part.toolCallId,
				result: response.result,
				isError: response.isError,
				...response.artifact !== void 0 && { artifact: response.artifact },
				...response.modelContent !== void 0 && { modelContent: response.modelContent }
			});
		};
		$[5] = messageId;
		$[6] = onAddToolResult;
		$[7] = part;
		$[8] = t4;
	} else t4 = $[8];
	let t5;
	if ($[9] !== messageId || $[10] !== onResumeToolCall || $[11] !== part || $[12] !== unstable_onRecordToolInteraction) {
		t5 = (payload) => {
			if (!onResumeToolCall) throw new Error("Runtime does not support resuming tool calls (onResumeToolCall is not set).");
			if (part.type !== "tool-call") throw new Error("Tried to resume tool call on non-tool message part");
			onResumeToolCall({
				toolCallId: part.toolCallId,
				payload
			});
			Promise.resolve().then(() => unstable_onRecordToolInteraction?.({
				messageId,
				toolCallId: part.toolCallId,
				interaction: createToolInteraction({
					type: "human-response",
					payload
				})
			})).catch(_temp4);
		};
		$[9] = messageId;
		$[10] = onResumeToolCall;
		$[11] = part;
		$[12] = unstable_onRecordToolInteraction;
		$[13] = t5;
	} else t5 = $[13];
	let t6;
	if ($[14] !== onRespondToToolApproval || $[15] !== part) {
		t6 = (response_0) => {
			if (!onRespondToToolApproval) throw new Error("Runtime does not support tool approvals.");
			if (part.type !== "tool-call") throw new Error("Tried to respond to tool approval on non-tool message part");
			if (!part.approval || part.approval.approved !== void 0 || part.approval.resolution !== void 0) throw new Error("Tool call has no pending approval");
			const options = resolveToolApprovalResponse(part.approval, response_0);
			try {
				return Promise.resolve(onRespondToToolApproval(options));
			} catch (t7) {
				const error = t7;
				return Promise.reject(error);
			}
		};
		$[14] = onRespondToToolApproval;
		$[15] = part;
		$[16] = t6;
	} else t6 = $[16];
	let t7;
	if ($[17] !== messageId || $[18] !== part || $[19] !== unstable_onRecordToolInteraction) {
		t7 = async (input) => {
			if (!unstable_onRecordToolInteraction) throw new Error("Runtime does not support recording tool interactions.");
			if (part.type !== "tool-call") throw new Error("Tried to record interaction on non-tool message part");
			await unstable_onRecordToolInteraction({
				messageId,
				toolCallId: part.toolCallId,
				interaction: createToolInteraction(input)
			});
		};
		$[17] = messageId;
		$[18] = part;
		$[19] = unstable_onRecordToolInteraction;
		$[20] = t7;
	} else t7 = $[20];
	let t8;
	if ($[21] !== t3 || $[22] !== t4 || $[23] !== t5 || $[24] !== t6 || $[25] !== t7) {
		t8 = {
			getState: t3,
			addToolResult: t4,
			resumeToolCall: t5,
			respondToToolApproval: t6,
			unstable_recordInteraction: t7
		};
		$[21] = t3;
		$[22] = t4;
		$[23] = t5;
		$[24] = t6;
		$[25] = t7;
		$[26] = t8;
	} else t8 = $[26];
	return t8;
};
const PartResource = resource(usePartResource);
const useAttachmentResource = ({ attachment, onRemove }) => {
	return {
		getState: () => attachment,
		remove: async () => {
			await onRemove?.();
		}
	};
};
const AttachmentResource = resource(useAttachmentResource);
const EMPTY_MESSAGE_KEYS = Object.freeze([]);
const useQueueItemClient = ({ item, onMove, onEdit, onRemove }) => {
	return {
		getState: () => item,
		steer: () => onMove({
			lane: "steer",
			insertAfter: null
		}),
		move: onMove,
		edit: onEdit,
		remove: onRemove
	};
};
const QueueItemClient = resource(useQueueItemClient);
const useLiveState = (initial) => {
	const $ = c(3);
	const [state, setState] = useState(initial);
	const ref = useRef(state);
	let t0;
	if ($[0] === Symbol.for("react.memo_cache_sentinel")) {
		t0 = (next) => {
			ref.current = typeof next === "function" ? next(ref.current) : next;
			setState(ref.current);
		};
		$[0] = t0;
	} else t0 = $[0];
	const set = t0;
	let t1;
	if ($[1] !== state) {
		t1 = [
			state,
			set,
			ref
		];
		$[1] = state;
		$[2] = t1;
	} else t1 = $[2];
	return t1;
};
const removeAttachmentThroughAdapter = async (attachment, attachmentAdapter, onError) => {
	try {
		await attachmentAdapter?.remove(attachment);
	} catch (error) {
		onError(error instanceof Error ? error.message : String(error));
		throw error;
	}
};
const dispatchSafely = (dispatch) => {
	try {
		dispatch();
		return;
	} catch (error) {
		return { error };
	}
};
const abortOnDestroy = (destroySignal, controller) => {
	if (!destroySignal) return () => {};
	const abort = () => controller.abort(destroySignal.reason);
	if (destroySignal.aborted) {
		abort();
		return () => {};
	}
	const unlink = () => {
		destroySignal.removeEventListener("abort", abort);
		controller.signal.removeEventListener("abort", unlink);
	};
	destroySignal.addEventListener("abort", abort, { once: true });
	controller.signal.addEventListener("abort", unlink, { once: true });
	return unlink;
};
const EMPTY_IN_TRANSIT = Object.freeze([]);
const useComposerClientResource = (t0) => {
	const $ = c(190);
	const { type, canCancel, isRunning: t1, isSendDisabled: t2, onCancel, onBeginEdit, onSend, message, queue, attachmentAdapter, messageKeys: t3 } = t0;
	const isRunning = t1 === void 0 ? false : t1;
	const isSendDisabled = t2 === void 0 ? false : t2;
	const messageKeys = t3 === void 0 ? EMPTY_MESSAGE_KEYS : t3;
	const [isEditing, setIsEditing, isEditingRef] = useLiveState(type === "thread");
	const [text, setText, textRef] = useLiveState("");
	const [role, setRole, roleRef] = useLiveState("user");
	let t4;
	if ($[0] === Symbol.for("react.memo_cache_sentinel")) {
		t4 = {};
		$[0] = t4;
	} else t4 = $[0];
	const [runConfig, setRunConfig, runConfigRef] = useLiveState(t4);
	let t5;
	if ($[1] === Symbol.for("react.memo_cache_sentinel")) {
		t5 = [];
		$[1] = t5;
	} else t5 = $[1];
	const [attachments, setAttachments, attachmentsRef] = useLiveState(t5);
	const [quote, setQuote, quoteRef] = useLiveState(void 0);
	let t6;
	if ($[2] === Symbol.for("react.memo_cache_sentinel")) {
		t6 = new AttachmentAddOperations();
		$[2] = t6;
	} else t6 = $[2];
	const attachmentAddOperations = t6;
	let t7;
	if ($[3] === Symbol.for("react.memo_cache_sentinel")) {
		t7 = new AttachmentSendOperations();
		$[3] = t7;
	} else t7 = $[3];
	const attachmentSends = t7;
	const destroySignal = useAssistantClientDestroySignal();
	const [submission, setSubmission, submissionRef] = useLiveState(void 0);
	const submissionSend = useRef(void 0);
	const [inTransit, setInTransit] = useLiveState(EMPTY_IN_TRANSIT);
	const messageKeysRef = useRef(messageKeys);
	const sendGeneration = useRef(0);
	let claimed;
	let landed;
	if ($[4] !== inTransit || $[5] !== messageKeys) {
		claimed = /* @__PURE__ */ new Set();
		landed = /* @__PURE__ */ new Set();
		for (const entry of inTransit) {
			const key = messageKeys.find((candidate) => !entry.known.has(candidate) && !claimed.has(candidate) && candidate.endsWith(`|${entry.submission.role}`));
			if (key === void 0) continue;
			claimed.add(key);
			landed.add(entry);
		}
		$[4] = inTransit;
		$[5] = messageKeys;
		$[6] = claimed;
		$[7] = landed;
	} else {
		claimed = $[6];
		landed = $[7];
	}
	let t8;
	if ($[8] !== claimed || $[9] !== landed) {
		t8 = {
			landed,
			claimed
		};
		$[8] = claimed;
		$[9] = landed;
		$[10] = t8;
	} else t8 = $[10];
	const shown = t8;
	let t9;
	if ($[11] !== inTransit || $[12] !== shown.landed) {
		let t10;
		if ($[14] !== shown.landed) {
			t10 = (entry_0) => !shown.landed.has(entry_0);
			$[14] = shown.landed;
			$[15] = t10;
		} else t10 = $[15];
		t9 = inTransit.filter(t10).map(_temp5);
		$[11] = inTransit;
		$[12] = shown.landed;
		$[13] = t9;
	} else t9 = $[13];
	const inTransitSubmissions = t9;
	let t10;
	if ($[16] !== messageKeys || $[17] !== setInTransit || $[18] !== shown.claimed || $[19] !== shown.landed) {
		t10 = () => {
			messageKeysRef.current = messageKeys;
			if (shown.landed.size === 0) return;
			setInTransit((prev) => prev.filter((entry_2) => !shown.landed.has(entry_2)).map((entry_3) => ({
				...entry_3,
				known: /* @__PURE__ */ new Set([...entry_3.known, ...shown.claimed])
			})));
		};
		$[16] = messageKeys;
		$[17] = setInTransit;
		$[18] = shown.claimed;
		$[19] = shown.landed;
		$[20] = t10;
	} else t10 = $[20];
	let t11;
	if ($[21] !== messageKeys || $[22] !== setInTransit || $[23] !== shown) {
		t11 = [
			messageKeys,
			shown,
			setInTransit
		];
		$[21] = messageKeys;
		$[22] = setInTransit;
		$[23] = shown;
		$[24] = t11;
	} else t11 = $[24];
	useEffect(t10, t11);
	let t12;
	if ($[25] !== message || $[26] !== setAttachments || $[27] !== setRole || $[28] !== setText) {
		t12 = () => {
			if (!message) return;
			const messageText = message.content.filter(_temp6).map(_temp7).join("\n\n");
			setText(messageText);
			setRole(message.role);
			const restored = message.attachments ?? [];
			for (const attachment of restored) attachmentSends.unmarkRemoved(attachment);
			setAttachments(restored);
		};
		$[25] = message;
		$[26] = setAttachments;
		$[27] = setRole;
		$[28] = setText;
		$[29] = t12;
	} else t12 = $[29];
	const updateFromMessage = t12;
	let t13;
	if ($[30] !== attachmentAdapter || $[31] !== setAttachments) {
		t13 = async (attachment_0) => {
			attachmentAddOperations.cancel(attachment_0.id);
			attachmentSends.markRemoved(attachment_0);
			if (!isAttachmentComplete(attachment_0)) await removeAttachmentThroughAdapter(attachment_0, attachmentAdapter, (message_0) => setAttachments((prev_0) => prev_0.map((candidate_0) => candidate_0.id === attachment_0.id && !isAttachmentComplete(candidate_0) ? attachmentSends.transfer(candidate_0, {
				...candidate_0,
				status: {
					type: "incomplete",
					reason: "error",
					message: message_0
				}
			}) : candidate_0)));
			setAttachments((prev_1) => prev_1.filter((a) => a.id !== attachment_0.id));
		};
		$[30] = attachmentAdapter;
		$[31] = setAttachments;
		$[32] = t13;
	} else t13 = $[32];
	const handleRemoveAttachment = t13;
	let t14;
	if ($[33] !== attachmentAdapter || $[34] !== setSubmission) {
		t14 = async (attachment_1) => {
			attachmentAddOperations.cancel(attachment_1.id);
			attachmentSends.markRemoved(attachment_1);
			if (!isAttachmentComplete(attachment_1)) await removeAttachmentThroughAdapter(attachment_1, attachmentAdapter, (message_1) => setSubmission((prev_2) => prev_2 ? {
				...prev_2,
				attachments: prev_2.attachments.map((candidate_1) => {
					if (candidate_1.id !== attachment_1.id || isAttachmentComplete(candidate_1)) return candidate_1;
					const failed = attachmentSends.transfer(candidate_1, {
						...candidate_1,
						status: {
							type: "incomplete",
							reason: "error",
							message: message_1
						}
					});
					attachmentSends.markRemoved(failed);
					return failed;
				})
			} : prev_2));
			setSubmission((prev_3) => prev_3 ? {
				...prev_3,
				attachments: prev_3.attachments.filter((a_0) => a_0.id !== attachment_1.id)
			} : prev_3);
		};
		$[33] = attachmentAdapter;
		$[34] = setSubmission;
		$[35] = t14;
	} else t14 = $[35];
	const handleRemoveSubmittedAttachment = t14;
	let t15;
	if ($[36] !== attachments || $[37] !== handleRemoveAttachment) {
		let t16;
		if ($[39] !== handleRemoveAttachment) {
			t16 = (attachment_2) => withKey(attachment_2.id, AttachmentResource({
				attachment: attachment_2,
				onRemove: () => handleRemoveAttachment(attachment_2)
			}));
			$[39] = handleRemoveAttachment;
			$[40] = t16;
		} else t16 = $[40];
		t15 = attachments.map(t16);
		$[36] = attachments;
		$[37] = handleRemoveAttachment;
		$[38] = t15;
	} else t15 = $[38];
	const attachmentClients = useClientLookup(t15);
	let t16;
	if ($[41] !== attachments || $[42] !== handleRemoveSubmittedAttachment || $[43] !== submission?.attachments) {
		let t17;
		if ($[45] !== attachments) {
			t17 = (attachment_3) => !attachments.some((a_1) => a_1.id === attachment_3.id);
			$[45] = attachments;
			$[46] = t17;
		} else t17 = $[46];
		let t18;
		if ($[47] !== handleRemoveSubmittedAttachment) {
			t18 = (attachment_4) => withKey(attachment_4.id, AttachmentResource({
				attachment: attachment_4,
				onRemove: () => handleRemoveSubmittedAttachment(attachment_4)
			}));
			$[47] = handleRemoveSubmittedAttachment;
			$[48] = t18;
		} else t18 = $[48];
		t16 = (submission?.attachments ?? []).filter(t17).map(t18);
		$[41] = attachments;
		$[42] = handleRemoveSubmittedAttachment;
		$[43] = submission?.attachments;
		$[44] = t16;
	} else t16 = $[44];
	const submittedAttachmentClients = useClientLookup(t16);
	let t17;
	if ($[49] !== attachmentAdapter) {
		t17 = async (removed) => {
			if (!attachmentAdapter) return;
			await Promise.all(removed.filter(_temp8).map(async (a_3) => attachmentAdapter.remove(a_3)));
		};
		$[49] = attachmentAdapter;
		$[50] = t17;
	} else t17 = $[50];
	const removePendingAttachments = t17;
	let t18;
	if ($[51] !== setAttachments || $[52] !== setSubmission || $[53] !== submissionRef) {
		t18 = (attachment_5) => {
			const current = submissionRef.current;
			if (current?.attachments.some((a_5) => a_5.id === attachment_5.id)) {
				setSubmission({
					...current,
					attachments: current.attachments.map((a_4) => a_4.id === attachment_5.id ? attachmentSends.transfer(a_4, attachment_5) : a_4)
				});
				return;
			}
			setAttachments((prev_4) => {
				const idx = prev_4.findIndex((a_6) => a_6.id === attachment_5.id);
				if (idx === -1) return [...prev_4, attachment_5];
				const next = [...prev_4];
				next[idx] = attachment_5;
				return next;
			});
		};
		$[51] = setAttachments;
		$[52] = setSubmission;
		$[53] = submissionRef;
		$[54] = t18;
	} else t18 = $[54];
	const upsertAttachment = t18;
	const steerItems = queue?.steerItems ?? EMPTY_QUEUE_ITEMS;
	const laneItems = queue?.items ?? EMPTY_QUEUE_ITEMS;
	let t19;
	if ($[55] !== laneItems || $[56] !== steerItems) {
		t19 = steerItems.length === 0 ? laneItems : laneItems.length === 0 ? steerItems : [...steerItems, ...laneItems];
		$[55] = laneItems;
		$[56] = steerItems;
		$[57] = t19;
	} else t19 = $[57];
	const queueItems = t19;
	let t20;
	if ($[58] !== queue || $[59] !== queueItems) {
		let t21;
		if ($[61] !== queue) {
			t21 = (item) => withKey(item.id, QueueItemClient({
				item,
				onMove: (placement) => queue?.move(item.id, placement),
				onEdit: (message_2) => queue?.edit(item.id, message_2),
				onRemove: () => queue?.remove(item.id)
			}));
			$[61] = queue;
			$[62] = t21;
		} else t21 = $[62];
		t20 = queueItems.map(t21);
		$[58] = queue;
		$[59] = queueItems;
		$[60] = t20;
	} else t20 = $[60];
	const queueItemClients = useClientLookup(t20);
	let t21;
	if ($[63] !== attachmentAdapter?.accept || $[64] !== attachmentClients.state || $[65] !== attachments.length || $[66] !== canCancel || $[67] !== inTransitSubmissions || $[68] !== isEditing || $[69] !== isSendDisabled || $[70] !== queueItems || $[71] !== quote || $[72] !== role || $[73] !== runConfig || $[74] !== submission || $[75] !== text || $[76] !== type) {
		t21 = () => {
			const isEmpty = !text.trim() && !attachments.length;
			return {
				text,
				role,
				attachments: attachmentClients.state,
				runConfig,
				isEditing,
				canCancel: canCancel || submission !== void 0,
				canSend: isEditing && !isEmpty && !isSendDisabled && submission === void 0,
				attachmentAccept: attachmentAdapter?.accept ?? "*",
				isEmpty,
				type,
				dictation: void 0,
				quote,
				queue: queueItems,
				submission,
				inTransit: inTransitSubmissions
			};
		};
		$[63] = attachmentAdapter?.accept;
		$[64] = attachmentClients.state;
		$[65] = attachments.length;
		$[66] = canCancel;
		$[67] = inTransitSubmissions;
		$[68] = isEditing;
		$[69] = isSendDisabled;
		$[70] = queueItems;
		$[71] = quote;
		$[72] = role;
		$[73] = runConfig;
		$[74] = submission;
		$[75] = text;
		$[76] = type;
		$[77] = t21;
	} else t21 = $[77];
	attachmentAdapter?.accept;
	let t22;
	if ($[78] !== t21) {
		t22 = t21();
		$[78] = t21;
		$[79] = t22;
	} else t22 = $[79];
	const state = t22;
	let t23;
	if ($[80] !== setSubmission) {
		t23 = () => {
			sendGeneration.current = sendGeneration.current + 1;
			submissionSend.current = void 0;
			setSubmission(void 0);
		};
		$[80] = setSubmission;
		$[81] = t23;
	} else t23 = $[81];
	const endSubmission = t23;
	let t24;
	if ($[82] !== setAttachments || $[83] !== setQuote || $[84] !== setText || $[85] !== type) {
		t24 = (content) => {
			if (type !== "thread") {
				const returned = new Map(content.attachments.map(_temp9));
				setAttachments((prev_5) => prev_5.map((attachment_7) => returned.get(attachment_7.id) ?? attachment_7));
				return;
			}
			const kept = content.attachments.filter((attachment_8) => !attachmentSends.isRemoved(attachment_8));
			setAttachments((prev_6) => [...kept, ...prev_6]);
			setText((prev_7) => [content.text, prev_7].filter(Boolean).join("\n"));
			setQuote((prev_8) => prev_8 ?? content.quote);
		};
		$[82] = setAttachments;
		$[83] = setQuote;
		$[84] = setText;
		$[85] = type;
		$[86] = t24;
	} else t24 = $[86];
	const returnToDraft = t24;
	let t25;
	if ($[87] !== endSubmission || $[88] !== returnToDraft || $[89] !== submissionRef) {
		t25 = () => {
			const current_0 = submissionRef.current;
			if (!current_0) return;
			submissionSend.current?.controller.abort();
			endSubmission();
			returnToDraft(current_0);
		};
		$[87] = endSubmission;
		$[88] = returnToDraft;
		$[89] = submissionRef;
		$[90] = t25;
	} else t25 = $[90];
	const cancelSubmission = t25;
	let t26;
	if ($[91] !== attachmentsRef || $[92] !== endSubmission || $[93] !== removePendingAttachments || $[94] !== submissionRef) {
		t26 = async () => {
			const current_1 = submissionRef.current;
			if (!current_1) return;
			submissionSend.current?.controller.abort();
			endSubmission();
			const drafted = new Set(attachmentsRef.current.map(_temp0));
			await removePendingAttachments(current_1.attachments.filter((attachment_9) => !drafted.has(attachment_9.id)));
		};
		$[91] = attachmentsRef;
		$[92] = endSubmission;
		$[93] = removePendingAttachments;
		$[94] = submissionRef;
		$[95] = t26;
	} else t26 = $[95];
	const discardSubmission = t26;
	let t27;
	if ($[96] !== endSubmission || $[97] !== returnToDraft || $[98] !== submissionRef) {
		t27 = (sent, settled, reason) => {
			const current_2 = submissionRef.current;
			if (!current_2) return;
			const failures = /* @__PURE__ */ new Map();
			settled.forEach((result, index) => {
				if (result.status === "rejected") failures.set(sent[index].id, result.reason);
			});
			const attachments_0 = current_2.attachments.map((attachment_10) => {
				if (!failures.has(attachment_10.id) || isAttachmentComplete(attachment_10)) return attachment_10;
				const failure = failures.get(attachment_10.id);
				return attachmentSends.transfer(attachment_10, {
					...attachment_10,
					status: {
						type: "incomplete",
						reason: "error",
						message: failure instanceof Error ? failure.message : String(failure)
					}
				});
			});
			endSubmission();
			returnToDraft({
				...current_2,
				attachments: attachments_0
			});
			console.error("Failed to send attachments", reason);
		};
		$[96] = endSubmission;
		$[97] = returnToDraft;
		$[98] = submissionRef;
		$[99] = t27;
	} else t27 = $[99];
	const returnSubmissionToDraft = t27;
	let t28;
	if ($[100] !== isRunning || $[101] !== onSend || $[102] !== queue || $[103] !== returnToDraft || $[104] !== setAttachments || $[105] !== setInTransit || $[106] !== setIsEditing || $[107] !== setSubmission || $[108] !== type) {
		t28 = (current_3, attachments_1, context, isSubmission) => {
			const composedMessage = {
				role: current_3.role,
				content: current_3.text ? [{
					type: "text",
					text: current_3.text
				}] : [],
				attachments: attachments_1,
				createdAt: /* @__PURE__ */ new Date(),
				parentId: null,
				sourceId: null,
				runConfig: context.runConfig,
				startRun: context.options?.startRun,
				metadata: { custom: { ...current_3.quote ? { quote: current_3.quote } : {} } }
			};
			const sent_0 = {
				...current_3,
				attachments: attachments_1
			};
			const queued = queue && type === "thread";
			if (isSubmission) {
				submissionSend.current = void 0;
				setSubmission(void 0);
			}
			if (isSubmission && type !== "thread") {
				const delivered = new Map(attachments_1.map(_temp1));
				setAttachments((prev_9) => prev_9.map((attachment_12) => delivered.get(attachment_12.id) ?? attachment_12));
			}
			const entry_4 = isSubmission && type === "thread" && !queued ? {
				submission: sent_0,
				known: new Set(messageKeysRef.current)
			} : void 0;
			if (entry_4) setInTransit((prev_10) => [...prev_10, entry_4]);
			const failure_0 = dispatchSafely(() => {
				if (queued) {
					if (context.options?.steer === true && queue.sendNow) queue.sendNow(composedMessage);
					else if (context.options?.steer ?? isRunning) queue.steer(composedMessage);
					else queue.enqueue(composedMessage);
				} else onSend?.(composedMessage);
			});
			if (failure_0) {
				console.error("[assistant-ui] Failed to send the message", failure_0.error);
				if (entry_4) setInTransit((prev_11) => prev_11.filter((candidate_2) => candidate_2 !== entry_4));
				returnToDraft(sent_0);
				return;
			}
			if (type === "edit") {
				attachmentAddOperations.cancelAll();
				setIsEditing(false);
			}
		};
		$[100] = isRunning;
		$[101] = onSend;
		$[102] = queue;
		$[103] = returnToDraft;
		$[104] = setAttachments;
		$[105] = setInTransit;
		$[106] = setIsEditing;
		$[107] = setSubmission;
		$[108] = type;
		$[109] = t28;
	} else t28 = $[109];
	const dispatchMessage = t28;
	let t29;
	if ($[110] !== attachmentAdapter || $[111] !== dispatchMessage || $[112] !== returnSubmissionToDraft || $[113] !== submissionRef) {
		t29 = async (generation) => {
			const context_0 = submissionSend.current;
			if (!context_0) return;
			const { signal } = context_0.controller;
			if (signal.aborted) return;
			const uploads = (submissionRef.current?.attachments ?? []).flatMap((attachment_13) => {
				const upload = attachmentAddOperations.whenSendable(attachment_13.id);
				return upload ? [upload] : [];
			});
			if (uploads.length > 0) {
				await Promise.all(uploads);
				if (generation !== sendGeneration.current || signal.aborted) return;
			}
			const current_4 = submissionRef.current;
			if (!current_4) return;
			const sent_1 = current_4.attachments.filter((attachment_14) => !attachmentSends.isRemoved(attachment_14));
			for (const attachment_15 of sent_1) attachmentAddOperations.cancel(attachment_15.id);
			const settled_0 = await Promise.allSettled(sent_1.map((attachment_16) => attachmentSends.send(attachment_16, attachmentAdapter, signal)));
			if (generation !== sendGeneration.current || signal.aborted) return;
			const rejection = settled_0.find(_temp10);
			if (rejection) {
				returnSubmissionToDraft(sent_1, settled_0, rejection.reason);
				return;
			}
			const finalAttachments = settled_0.flatMap((result_1, index_0) => attachmentSends.isRemoved(sent_1[index_0]) || result_1.status === "rejected" ? [] : [result_1.value]);
			dispatchMessage(submissionRef.current ?? current_4, finalAttachments, context_0, true);
		};
		$[110] = attachmentAdapter;
		$[111] = dispatchMessage;
		$[112] = returnSubmissionToDraft;
		$[113] = submissionRef;
		$[114] = t29;
	} else t29 = $[114];
	const prepareSubmission = t29;
	let t30;
	if ($[115] !== state) {
		t30 = () => state;
		$[115] = state;
		$[116] = t30;
	} else t30 = $[116];
	let t31;
	if ($[117] !== attachmentAdapter || $[118] !== setAttachments || $[119] !== upsertAttachment) {
		t31 = async (fileOrAttachment) => {
			if (attachmentAdapter) {
				const file = isCreateAttachment(fileOrAttachment) ? {
					name: fileOrAttachment.name,
					type: fileOrAttachment.contentType ?? ""
				} : {
					name: fileOrAttachment.name,
					type: fileOrAttachment.type
				};
				if (!fileMatchesAccept(file, attachmentAdapter.accept)) throw new Error(`File type ${file.type || "unknown"} is not accepted. Accepted types: ${attachmentAdapter.accept}`);
			}
			if (!isCreateAttachment(fileOrAttachment) && attachmentAdapter) {
				const operation = attachmentAddOperations.start();
				try {
					await drainAttachmentAdd(attachmentAdapter.add({ file: fileOrAttachment }), (attachment_17) => {
						if (!attachmentAddOperations.accept(operation, attachment_17)) return false;
						upsertAttachment(attachment_17);
						return true;
					});
					attachmentAddOperations.finish(operation);
				} catch (t32) {
					const error = t32;
					attachmentAddOperations.finish(operation);
					if (!attachmentAddOperations.isCancelled(operation)) throw error;
				}
			} else if (!isCreateAttachment(fileOrAttachment)) {
				const newAttachment = {
					id: generateId(),
					type: "file",
					name: fileOrAttachment.name,
					contentType: fileOrAttachment.type,
					file: fileOrAttachment,
					status: { type: "complete" },
					content: []
				};
				setAttachments((prev_12) => [...prev_12, newAttachment]);
			} else {
				const newAttachment_0 = {
					id: fileOrAttachment.id ?? generateId(),
					type: fileOrAttachment.type ?? "document",
					name: fileOrAttachment.name,
					contentType: fileOrAttachment.contentType,
					content: fileOrAttachment.content,
					status: { type: "complete" }
				};
				setAttachments((prev_13) => [...prev_13, newAttachment_0]);
			}
		};
		$[117] = attachmentAdapter;
		$[118] = setAttachments;
		$[119] = upsertAttachment;
		$[120] = t31;
	} else t31 = $[120];
	let t32;
	if ($[121] !== attachmentsRef || $[122] !== removePendingAttachments || $[123] !== setAttachments || $[124] !== submissionRef) {
		t32 = async () => {
			attachmentAddOperations.cancelAll();
			const removed_0 = attachmentsRef.current;
			if (submissionRef.current) for (const attachment_18 of removed_0) attachmentSends.markRemoved(attachment_18);
			setAttachments([]);
			await removePendingAttachments(removed_0);
		};
		$[121] = attachmentsRef;
		$[122] = removePendingAttachments;
		$[123] = setAttachments;
		$[124] = submissionRef;
		$[125] = t32;
	} else t32 = $[125];
	let t33;
	if ($[126] !== attachmentClients || $[127] !== attachments || $[128] !== submission?.attachments || $[129] !== submittedAttachmentClients) {
		t33 = (selector) => {
			if ("id" in selector) {
				const submitted = submission?.attachments.some((attachment_19) => attachment_19.id === selector.id);
				const inDraft = attachments.some((attachment_20) => attachment_20.id === selector.id);
				if (submitted && !inDraft) return submittedAttachmentClients.get({ key: selector.id });
				return attachmentClients.get({ key: selector.id });
			}
			return attachmentClients.get(selector);
		};
		$[126] = attachmentClients;
		$[127] = attachments;
		$[128] = submission?.attachments;
		$[129] = submittedAttachmentClients;
		$[130] = t33;
	} else t33 = $[130];
	let t34;
	if ($[131] !== attachmentsRef || $[132] !== discardSubmission || $[133] !== removePendingAttachments || $[134] !== setAttachments || $[135] !== setQuote || $[136] !== setRole || $[137] !== setRunConfig || $[138] !== setText) {
		t34 = async () => {
			attachmentAddOperations.cancelAll();
			sendGeneration.current = sendGeneration.current + 1;
			const discarded = discardSubmission();
			const removed_1 = attachmentsRef.current;
			setText("");
			setRole("user");
			setRunConfig({});
			setAttachments([]);
			setQuote(void 0);
			await Promise.all([removePendingAttachments(removed_1), discarded]);
		};
		$[131] = attachmentsRef;
		$[132] = discardSubmission;
		$[133] = removePendingAttachments;
		$[134] = setAttachments;
		$[135] = setQuote;
		$[136] = setRole;
		$[137] = setRunConfig;
		$[138] = setText;
		$[139] = t34;
	} else t34 = $[139];
	let t35;
	if ($[140] !== attachmentsRef || $[141] !== destroySignal || $[142] !== dispatchMessage || $[143] !== isEditingRef || $[144] !== isSendDisabled || $[145] !== prepareSubmission || $[146] !== quoteRef || $[147] !== roleRef || $[148] !== runConfigRef || $[149] !== setAttachments || $[150] !== setQuote || $[151] !== setSubmission || $[152] !== setText || $[153] !== submissionRef || $[154] !== textRef || $[155] !== type) {
		t35 = (opts) => {
			const currentAttachments = attachmentsRef.current.filter((attachment_21) => !attachmentSends.isRemoved(attachment_21));
			const isEmpty_0 = !textRef.current.trim() && !currentAttachments.length;
			if (!isEditingRef.current) throw new Error("Composer is not available");
			if (isEmpty_0 || isSendDisabled || submissionRef.current) return;
			const submitted_0 = {
				id: generateId(),
				role: roleRef.current,
				text: textRef.current,
				quote: quoteRef.current,
				attachments: currentAttachments
			};
			const context_1 = {
				options: opts,
				runConfig: runConfigRef.current
			};
			const complete = currentAttachments.filter(isAttachmentComplete);
			const controller = complete.length === currentAttachments.length ? void 0 : new AbortController();
			if (controller) {
				submissionSend.current = {
					...context_1,
					controller
				};
				setSubmission(submitted_0);
			}
			if (type === "thread") {
				const detached = new Set(currentAttachments);
				setAttachments((prev_14) => prev_14.filter((attachment_22) => !detached.has(attachment_22)));
				setText("");
				setQuote(void 0);
			}
			const generation_0 = sendGeneration.current = sendGeneration.current + 1;
			if (!controller) {
				dispatchMessage(submitted_0, complete, context_1, false);
				return;
			}
			const release = abortOnDestroy(destroySignal, controller);
			prepareSubmission(generation_0).finally(release);
		};
		$[140] = attachmentsRef;
		$[141] = destroySignal;
		$[142] = dispatchMessage;
		$[143] = isEditingRef;
		$[144] = isSendDisabled;
		$[145] = prepareSubmission;
		$[146] = quoteRef;
		$[147] = roleRef;
		$[148] = runConfigRef;
		$[149] = setAttachments;
		$[150] = setQuote;
		$[151] = setSubmission;
		$[152] = setText;
		$[153] = submissionRef;
		$[154] = textRef;
		$[155] = type;
		$[156] = t35;
	} else t35 = $[156];
	let t36;
	if ($[157] !== attachmentsRef || $[158] !== canCancel || $[159] !== cancelSubmission || $[160] !== discardSubmission || $[161] !== onCancel || $[162] !== removePendingAttachments || $[163] !== setAttachments || $[164] !== setIsEditing || $[165] !== submissionRef || $[166] !== type) {
		t36 = () => {
			if (type === "thread" && submissionRef.current) {
				cancelSubmission();
				if (canCancel) onCancel?.();
				return;
			}
			if (type === "edit") {
				attachmentAddOperations.cancelAll();
				sendGeneration.current = sendGeneration.current + 1;
				discardSubmission();
				const removed_2 = attachmentsRef.current;
				setAttachments([]);
				removePendingAttachments(removed_2).catch(_temp11);
			}
			onCancel?.();
			if (type === "edit") setIsEditing(false);
		};
		$[157] = attachmentsRef;
		$[158] = canCancel;
		$[159] = cancelSubmission;
		$[160] = discardSubmission;
		$[161] = onCancel;
		$[162] = removePendingAttachments;
		$[163] = setAttachments;
		$[164] = setIsEditing;
		$[165] = submissionRef;
		$[166] = type;
		$[167] = t36;
	} else t36 = $[167];
	let t37;
	if ($[168] !== isEditingRef || $[169] !== onBeginEdit || $[170] !== setIsEditing || $[171] !== type || $[172] !== updateFromMessage) {
		t37 = () => {
			onBeginEdit?.();
			if (type === "thread") return;
			if (isEditingRef.current) throw new Error("Edit already in progress");
			setIsEditing(true);
			updateFromMessage();
		};
		$[168] = isEditingRef;
		$[169] = onBeginEdit;
		$[170] = setIsEditing;
		$[171] = type;
		$[172] = updateFromMessage;
		$[173] = t37;
	} else t37 = $[173];
	let t38;
	if ($[174] !== queueItemClients) {
		t38 = (selector_0) => {
			if ("id" in selector_0) return queueItemClients.get({ key: selector_0.id });
			return queueItemClients.get(selector_0);
		};
		$[174] = queueItemClients;
		$[175] = t38;
	} else t38 = $[175];
	let t39;
	if ($[176] !== setQuote || $[177] !== setRole || $[178] !== setRunConfig || $[179] !== setText || $[180] !== t30 || $[181] !== t31 || $[182] !== t32 || $[183] !== t33 || $[184] !== t34 || $[185] !== t35 || $[186] !== t36 || $[187] !== t37 || $[188] !== t38) {
		t39 = {
			getState: t30,
			setText,
			setRole,
			setRunConfig,
			addAttachment: t31,
			clearAttachments: t32,
			attachment: t33,
			reset: t34,
			send: t35,
			cancel: t36,
			beginEdit: t37,
			startDictation: _temp12,
			stopDictation: _temp13,
			setQuote,
			queueItem: t38
		};
		$[176] = setQuote;
		$[177] = setRole;
		$[178] = setRunConfig;
		$[179] = setText;
		$[180] = t30;
		$[181] = t31;
		$[182] = t32;
		$[183] = t33;
		$[184] = t34;
		$[185] = t35;
		$[186] = t36;
		$[187] = t37;
		$[188] = t38;
		$[189] = t39;
	} else t39 = $[189];
	return t39;
};
const ComposerClientResource = resource(useComposerClientResource);
const createSpeechController = (notify) => {
	let session;
	const clear = () => {
		if (!session) return;
		session.cancel();
		session = void 0;
		notify(void 0);
	};
	return {
		speak: (adapter, message) => {
			clear();
			const utterance = adapter.speak(getThreadMessageText(message));
			let unsub;
			unsub = utterance.subscribe(() => {
				if (utterance.status.type === "ended") {
					unsub?.();
					session = void 0;
					notify(void 0);
				} else notify({
					messageId: message.id,
					status: utterance.status
				});
			});
			if (utterance.status.type === "ended") {
				unsub();
				notify(void 0);
				return;
			}
			session = {
				messageId: message.id,
				cancel: () => {
					unsub();
					utterance.cancel();
				}
			};
			notify({
				messageId: message.id,
				status: utterance.status
			});
		},
		stop: () => {
			if (!session) throw new Error("No message is being spoken");
			clear();
		},
		stopMessage: (messageId) => {
			if (session?.messageId !== messageId) throw new Error("Message is not being spoken");
			clear();
		},
		dispose: clear
	};
};
const dedupeMessagesById = (messages) => {
	const seenIds = /* @__PURE__ */ new Set();
	const deduped = [];
	for (let i = messages.length - 1; i >= 0; i--) {
		const message = messages[i];
		if (seenIds.has(message.id)) {
			console.warn(`ExternalThread: duplicate message id "${message.id}" in the provided messages array; keeping the last occurrence.`);
			continue;
		}
		seenIds.add(message.id);
		deduped.push(message);
	}
	return deduped.length === messages.length ? messages : deduped.reverse();
};
const useExternalThread = (t0) => {
	const $ = c(147);
	const { messages: messagesProp, isRunning: t1, isLoading: t2, state: threadState, extras, isSendDisabled: t3, onNew, onEdit, onReload, onStartRun, onCancel, onResume, onRefetchThread, onAddToolResult, onResumeToolCall, unstable_onRecordToolInteraction, onLoadExternalState, attachmentAdapter, feedbackAdapter, speechAdapter, queue, branches, onRespondToToolApproval } = t0;
	const isRunning = t1 === void 0 ? false : t1;
	const isLoading = t2 === void 0 ? false : t2;
	const isSendDisabled = t3 === void 0 ? false : t3;
	let t4;
	if ($[0] !== messagesProp) {
		t4 = dedupeMessagesById(messagesProp);
		$[0] = messagesProp;
		$[1] = t4;
	} else t4 = $[1];
	const messages = t4;
	let t5;
	if ($[2] === Symbol.for("react.memo_cache_sentinel")) {
		t5 = {};
		$[2] = t5;
	} else t5 = $[2];
	const [submittedFeedback, setSubmittedFeedback] = useState(t5);
	let t6;
	if ($[3] !== submittedFeedback) {
		t6 = (msg) => {
			const entry = submittedFeedback[msg.id];
			const external = msg.metadata.submittedFeedback;
			return entry && external?.type === entry.external?.type && external?.comment === entry.external?.comment ? entry.feedback : void 0;
		};
		$[3] = submittedFeedback;
		$[4] = t6;
	} else t6 = $[4];
	const feedbackFor = t6;
	let t7;
	let t8;
	if ($[5] !== messages) {
		t7 = () => {
			setSubmittedFeedback((prev) => {
				const live = Object.entries(prev).filter((t9) => {
					const [id, entry_0] = t9;
					const msg_0 = messages.find((m) => m.id === id);
					return !!msg_0 && msg_0.metadata.submittedFeedback?.type === entry_0.external?.type && msg_0.metadata.submittedFeedback?.comment === entry_0.external?.comment;
				});
				return live.length === Object.keys(prev).length ? prev : Object.fromEntries(live);
			});
		};
		t8 = [messages];
		$[5] = messages;
		$[6] = t7;
		$[7] = t8;
	} else {
		t7 = $[6];
		t8 = $[7];
	}
	useEffect(t7, t8);
	let t9;
	if ($[8] !== feedbackAdapter) {
		t9 = (message, feedback) => {
			const comment = feedback.comment?.trim();
			const submittedFeedback_0 = {
				type: feedback.type,
				...comment ? { comment } : void 0
			};
			feedbackAdapter?.submit({
				message,
				...submittedFeedback_0
			});
			if (message.role === "assistant") setSubmittedFeedback((prev_0) => ({
				...prev_0,
				[message.id]: {
					feedback: submittedFeedback_0,
					external: message.metadata.submittedFeedback
				}
			}));
		};
		$[8] = feedbackAdapter;
		$[9] = t9;
	} else t9 = $[9];
	const handleSubmitFeedback = t9;
	const [speechState, setSpeech] = useState(void 0);
	let t10;
	if ($[10] === Symbol.for("react.memo_cache_sentinel")) {
		t10 = () => createSpeechController(setSpeech);
		$[10] = t10;
	} else t10 = $[10];
	const [speechController] = useState(t10);
	const hasSpeechAdapter = !!speechAdapter;
	const speech = hasSpeechAdapter ? speechState : void 0;
	let t11;
	let t12;
	if ($[11] !== hasSpeechAdapter || $[12] !== speechController) {
		t11 = () => {
			if (!hasSpeechAdapter) speechController.dispose();
		};
		t12 = [hasSpeechAdapter, speechController];
		$[11] = hasSpeechAdapter;
		$[12] = speechController;
		$[13] = t11;
		$[14] = t12;
	} else {
		t11 = $[13];
		t12 = $[14];
	}
	useEffect(t11, t12);
	let t13;
	let t14;
	if ($[15] !== speechController) {
		t13 = () => () => speechController.dispose();
		t14 = [speechController];
		$[15] = speechController;
		$[16] = t13;
		$[17] = t14;
	} else {
		t13 = $[16];
		t14 = $[17];
	}
	useEffect(t13, t14);
	let t15;
	if ($[18] !== speechAdapter || $[19] !== speechController) {
		t15 = (message_0) => {
			if (!speechAdapter) throw new Error("Speech adapter not configured");
			speechController.speak(speechAdapter, message_0);
		};
		$[18] = speechAdapter;
		$[19] = speechController;
		$[20] = t15;
	} else t15 = $[20];
	const handleSpeak = t15;
	let t16;
	if ($[21] !== messages || $[22] !== onReload) {
		t16 = (messageId) => {
			const messageIndex = messages.findIndex((m_0) => m_0.id === messageId);
			if (messageIndex === -1) return;
			const parentId = messageIndex > 0 ? messages[messageIndex - 1].id : null;
			onReload?.(parentId);
		};
		$[21] = messages;
		$[22] = onReload;
		$[23] = t16;
	} else t16 = $[23];
	const handleReload = t16;
	let t17;
	if ($[24] !== messages) {
		t17 = messages.map(_temp14);
		$[24] = messages;
		$[25] = t17;
	} else t17 = $[25];
	const messageKeys = t17;
	let t18;
	if ($[26] !== onCancel || $[27] !== queue) {
		t18 = () => {
			if (!onCancel) return;
			queue?.__internal_notifyCancelled?.();
			onCancel();
		};
		$[26] = onCancel;
		$[27] = queue;
		$[28] = t18;
	} else t18 = $[28];
	const handleCancelRun = t18;
	let t19;
	if ($[29] !== messages || $[30] !== onNew) {
		t19 = (message_2) => {
			onNew?.({
				...message_2,
				parentId: messages.at(-1)?.id ?? null
			});
		};
		$[29] = messages;
		$[30] = onNew;
		$[31] = t19;
	} else t19 = $[31];
	const handleSendNew = t19;
	let t20;
	if ($[32] !== messages) {
		t20 = messages.at(-1)?.id ?? null;
		$[32] = messages;
		$[33] = t20;
	} else t20 = $[33];
	const headId = t20;
	const hasCancel = !!onCancel;
	const hasRefetchThread = !!onRefetchThread;
	let t21;
	if ($[34] !== headId || $[35] !== queue) {
		t21 = queue && {
			...queue,
			enqueue: (message_3) => queue.enqueue({
				...message_3,
				parentId: message_3.parentId ?? headId
			}),
			steer: (message_4) => queue.steer({
				...message_4,
				parentId: message_4.parentId ?? headId
			}),
			...queue.sendNow !== void 0 && { sendNow: (message_5) => queue.sendNow?.({
				...message_5,
				parentId: message_5.parentId ?? headId
			}) }
		};
		$[34] = headId;
		$[35] = queue;
		$[36] = t21;
	} else t21 = $[36];
	const composerQueue = t21;
	const t22 = isRunning && hasCancel;
	let t23;
	if ($[37] !== attachmentAdapter || $[38] !== composerQueue || $[39] !== handleCancelRun || $[40] !== handleSendNew || $[41] !== isRunning || $[42] !== isSendDisabled || $[43] !== messageKeys || $[44] !== t22) {
		t23 = ComposerClientResource({
			type: "thread",
			canCancel: t22,
			isRunning,
			isSendDisabled,
			onCancel: handleCancelRun,
			onSend: handleSendNew,
			queue: composerQueue,
			attachmentAdapter,
			messageKeys
		});
		$[37] = attachmentAdapter;
		$[38] = composerQueue;
		$[39] = handleCancelRun;
		$[40] = handleSendNew;
		$[41] = isRunning;
		$[42] = isSendDisabled;
		$[43] = messageKeys;
		$[44] = t22;
		$[45] = t23;
	} else t23 = $[45];
	const composerClient = useClientResource(t23);
	const submission = composerClient.state.submission;
	const inTransit = composerClient.state.inTransit;
	let t24;
	if ($[46] !== inTransit) {
		t24 = inTransit ?? [];
		$[46] = inTransit;
		$[47] = t24;
	} else t24 = $[47];
	let t25;
	if ($[48] !== submission) {
		t25 = submission ? [submission] : [];
		$[48] = submission;
		$[49] = t25;
	} else t25 = $[49];
	let t26;
	if ($[50] !== t24 || $[51] !== t25) {
		t26 = [...t24, ...t25];
		$[50] = t24;
		$[51] = t25;
		$[52] = t26;
	} else t26 = $[52];
	const pending = t26;
	const hasPending = pending.length > 0;
	let t27;
	if ($[53] !== attachmentAdapter || $[54] !== branches || $[55] !== feedbackFor || $[56] !== handleReload || $[57] !== handleSpeak || $[58] !== handleSubmitFeedback || $[59] !== hasPending || $[60] !== messages || $[61] !== onAddToolResult || $[62] !== onEdit || $[63] !== onRespondToToolApproval || $[64] !== onResumeToolCall || $[65] !== queue || $[66] !== speech || $[67] !== speechController || $[68] !== unstable_onRecordToolInteraction) {
		t27 = messages.map((msg_1, index) => {
			const props = {
				message: msg_1,
				index,
				isLast: index === messages.length - 1 && !hasPending,
				parentId: index > 0 ? messages[index - 1].id : null,
				onReload: () => handleReload(msg_1.id),
				queue,
				branches,
				onRespondToToolApproval,
				unstable_onRecordToolInteraction,
				onAddToolResult,
				onResumeToolCall,
				attachmentAdapter,
				submittedFeedback: feedbackFor(msg_1),
				onSubmitFeedback: (feedback_0) => handleSubmitFeedback(msg_1, feedback_0),
				speech: speech?.messageId === msg_1.id ? speech : void 0,
				onSpeak: () => handleSpeak(msg_1),
				onStopSpeaking: () => speechController.stopMessage(msg_1.id)
			};
			if (onEdit) props.onEdit = onEdit;
			return withKey(msg_1.id, MessageClient(props));
		});
		$[53] = attachmentAdapter;
		$[54] = branches;
		$[55] = feedbackFor;
		$[56] = handleReload;
		$[57] = handleSpeak;
		$[58] = handleSubmitFeedback;
		$[59] = hasPending;
		$[60] = messages;
		$[61] = onAddToolResult;
		$[62] = onEdit;
		$[63] = onRespondToToolApproval;
		$[64] = onResumeToolCall;
		$[65] = queue;
		$[66] = speech;
		$[67] = speechController;
		$[68] = unstable_onRecordToolInteraction;
		$[69] = t27;
	} else t27 = $[69];
	const messageClients = useClientLookup(t27);
	let t28;
	if ($[70] !== pending) {
		t28 = pending.map(submissionThreadMessage);
		$[70] = pending;
		$[71] = t28;
	} else t28 = $[71];
	const pendingMessages = t28;
	let t29;
	if ($[72] !== messages.length || $[73] !== pending || $[74] !== pendingMessages) {
		t29 = pending.map((row, index_0) => withKey(row.id, ThreadMessageClient({
			message: pendingMessages[index_0],
			submission: row,
			index: messages.length + index_0,
			isLast: index_0 === pending.length - 1
		}), [
			pendingMessages[index_0],
			row,
			messages.length,
			index_0,
			pending.length
		]));
		$[72] = messages.length;
		$[73] = pending;
		$[74] = pendingMessages;
		$[75] = t29;
	} else t29 = $[75];
	const pendingClients = useClientLookup(t29);
	let t30;
	if ($[76] === Symbol.for("react.memo_cache_sentinel")) {
		t30 = createTaskDeriver();
		$[76] = t30;
	} else t30 = $[76];
	const taskDeriver = t30;
	let t31;
	if ($[77] !== messages) {
		t31 = taskDeriver(messages);
		$[77] = messages;
		$[78] = t31;
	} else t31 = $[78];
	const tasks = t31;
	let t32;
	if ($[79] !== tasks) {
		t32 = tasks.map(_temp15);
		$[79] = tasks;
		$[80] = t32;
	} else t32 = $[80];
	const taskClients = useClientLookup(t32);
	let t33;
	if ($[81] === Symbol.for("react.memo_cache_sentinel")) {
		t33 = ThreadSuggestions(EMPTY_SUGGESTIONS);
		$[81] = t33;
	} else t33 = $[81];
	const suggestionsClient = useClientResource(t33);
	const hasQueue = !!queue;
	const hasBranches = !!branches;
	const hasEdit = !!onEdit;
	const hasReload = !!onReload;
	const hasAttachments = !!attachmentAdapter;
	const hasFeedback = !!feedbackAdapter;
	const hasSpeech = !!speechAdapter;
	const hasAnswerToolCall = !!onAddToolResult || !!onResumeToolCall || !!onRespondToToolApproval;
	let t34;
	if ($[82] !== messageClients.state || $[83] !== pendingClients.state) {
		t34 = pendingClients.state.length === 0 ? messageClients.state : [...messageClients.state, ...pendingClients.state];
		$[82] = messageClients.state;
		$[83] = pendingClients.state;
		$[84] = t34;
	} else t34 = $[84];
	const messageStates = t34;
	const t35 = messageStates.length === 0 && !isLoading;
	let t36;
	if ($[85] !== hasAnswerToolCall || $[86] !== hasAttachments || $[87] !== hasBranches || $[88] !== hasCancel || $[89] !== hasEdit || $[90] !== hasFeedback || $[91] !== hasQueue || $[92] !== hasRefetchThread || $[93] !== hasReload || $[94] !== hasSpeech) {
		t36 = {
			edit: hasEdit,
			delete: false,
			reload: hasReload,
			refetchThread: hasRefetchThread,
			cancel: hasCancel,
			speech: hasSpeech,
			attachments: hasAttachments,
			feedback: hasFeedback,
			voice: false,
			switchToBranch: hasBranches,
			switchBranchDuringRun: false,
			unstable_copy: false,
			dictation: false,
			queue: hasQueue,
			answerToolCall: hasAnswerToolCall
		};
		$[85] = hasAnswerToolCall;
		$[86] = hasAttachments;
		$[87] = hasBranches;
		$[88] = hasCancel;
		$[89] = hasEdit;
		$[90] = hasFeedback;
		$[91] = hasQueue;
		$[92] = hasRefetchThread;
		$[93] = hasReload;
		$[94] = hasSpeech;
		$[95] = t36;
	} else t36 = $[95];
	let t37;
	if ($[96] !== threadState) {
		t37 = threadState ?? {};
		$[96] = threadState;
		$[97] = t37;
	} else t37 = $[97];
	let t38;
	if ($[98] !== composerClient.state || $[99] !== extras || $[100] !== isLoading || $[101] !== isRunning || $[102] !== messageStates || $[103] !== speech || $[104] !== t35 || $[105] !== t36 || $[106] !== t37 || $[107] !== tasks) {
		t38 = {
			isEmpty: t35,
			isDisabled: false,
			isLoading,
			isRunning,
			capabilities: t36,
			messages: messageStates,
			tasks,
			state: t37,
			suggestions: EMPTY_SUGGESTIONS,
			extras,
			speech,
			voice: void 0,
			composer: composerClient.state
		};
		$[98] = composerClient.state;
		$[99] = extras;
		$[100] = isLoading;
		$[101] = isRunning;
		$[102] = messageStates;
		$[103] = speech;
		$[104] = t35;
		$[105] = t36;
		$[106] = t37;
		$[107] = tasks;
		$[108] = t38;
	} else t38 = $[108];
	const state = t38;
	let t39;
	if ($[109] !== state) {
		t39 = () => state;
		$[109] = state;
		$[110] = t39;
	} else t39 = $[110];
	let t40;
	if ($[111] !== composerClient.methods) {
		t40 = () => composerClient.methods;
		$[111] = composerClient.methods;
		$[112] = t40;
	} else t40 = $[112];
	let t41;
	if ($[113] !== suggestionsClient) {
		t41 = () => suggestionsClient.methods;
		$[113] = suggestionsClient;
		$[114] = t41;
	} else t41 = $[114];
	let t42;
	if ($[115] !== taskClients || $[116] !== tasks) {
		t42 = (selector) => {
			if ("id" in selector) {
				const task_0 = tasks.find((candidate) => candidate.id === selector.id);
				return taskClients.get({ key: task_0 ? getTaskKey(task_0) : selector.id });
			}
			return taskClients.get(selector);
		};
		$[115] = taskClients;
		$[116] = tasks;
		$[117] = t42;
	} else t42 = $[117];
	let t43;
	if ($[118] !== messages || $[119] !== onNew || $[120] !== queue) {
		t43 = (message_6) => {
			const appendMessage = typeof message_6 === "string" ? {
				createdAt: /* @__PURE__ */ new Date(),
				parentId: messages.at(-1)?.id ?? null,
				sourceId: null,
				runConfig: {},
				role: "user",
				content: [{
					type: "text",
					text: message_6
				}],
				attachments: [],
				metadata: { custom: {} }
			} : {
				createdAt: message_6.createdAt ?? /* @__PURE__ */ new Date(),
				parentId: message_6.parentId === void 0 ? messages.at(-1)?.id ?? null : message_6.parentId,
				sourceId: message_6.sourceId ?? null,
				role: message_6.role ?? "user",
				content: message_6.content,
				attachments: message_6.attachments ?? [],
				metadata: message_6.metadata ?? { custom: {} },
				runConfig: message_6.runConfig ?? {},
				startRun: message_6.startRun
			};
			if (queue) queue.enqueue(appendMessage);
			else onNew?.(appendMessage);
		};
		$[118] = messages;
		$[119] = onNew;
		$[120] = queue;
		$[121] = t43;
	} else t43 = $[121];
	let t44;
	if ($[122] !== onStartRun) {
		t44 = () => {
			onStartRun?.();
		};
		$[122] = onStartRun;
		$[123] = t44;
	} else t44 = $[123];
	let t45;
	if ($[124] !== onResume) {
		t45 = () => {
			if (!onResume) throw new Error("Runtime does not support resuming runs (onResume is not set).");
			onResume();
		};
		$[124] = onResume;
		$[125] = t45;
	} else t45 = $[125];
	let t46;
	if ($[126] !== onRefetchThread) {
		t46 = onRefetchThread && { unstable_refetchThread: onRefetchThread };
		$[126] = onRefetchThread;
		$[127] = t46;
	} else t46 = $[127];
	let t47;
	if ($[128] !== onLoadExternalState) {
		t47 = (state_0) => {
			if (!onLoadExternalState) throw new Error("Runtime does not support importing external states (onLoadExternalState is not set).");
			onLoadExternalState(state_0);
		};
		$[128] = onLoadExternalState;
		$[129] = t47;
	} else t47 = $[129];
	let t48;
	if ($[130] !== messageClients || $[131] !== pending || $[132] !== pendingClients) {
		t48 = (selector_0) => {
			if ("id" in selector_0) {
				if (pending.some((row_0) => row_0.id === selector_0.id)) return pendingClients.get({ key: selector_0.id });
				return messageClients.get({ key: selector_0.id });
			}
			if (selector_0.index >= messageClients.state.length) return pendingClients.get({ index: selector_0.index - messageClients.state.length });
			return messageClients.get(selector_0);
		};
		$[130] = messageClients;
		$[131] = pending;
		$[132] = pendingClients;
		$[133] = t48;
	} else t48 = $[133];
	let t49;
	if ($[134] !== handleCancelRun || $[135] !== speechController.stop || $[136] !== t39 || $[137] !== t40 || $[138] !== t41 || $[139] !== t42 || $[140] !== t43 || $[141] !== t44 || $[142] !== t45 || $[143] !== t46 || $[144] !== t47 || $[145] !== t48) {
		t49 = {
			getState: t39,
			composer: t40,
			suggestions: t41,
			task: t42,
			append: t43,
			deleteMessage: _temp16,
			startRun: t44,
			resumeRun: t45,
			cancelRun: handleCancelRun,
			...t46,
			importExternalState: t47,
			getModelContext: _temp17,
			export: _temp18,
			import: _temp19,
			reset: _temp20,
			message: t48,
			stopSpeaking: speechController.stop,
			connectVoice: _temp21,
			disconnectVoice: _temp22,
			getVoiceVolume: _temp23,
			subscribeVoiceVolume: _temp25,
			muteVoice: _temp26,
			unmuteVoice: _temp27
		};
		$[134] = handleCancelRun;
		$[135] = speechController.stop;
		$[136] = t39;
		$[137] = t40;
		$[138] = t41;
		$[139] = t42;
		$[140] = t43;
		$[141] = t44;
		$[142] = t45;
		$[143] = t46;
		$[144] = t47;
		$[145] = t48;
		$[146] = t49;
	} else t49 = $[146];
	return t49;
};
const ExternalThread = resource(useExternalThread);
attachTransformScopes(useExternalThread, (scopes, parent) => {
	if (!scopes.threads && parent.threads.source === null) {
		const threadElement = scopes.thread;
		scopes.threads = SingleThreadList({ thread: threadElement });
		delete scopes.thread;
		scopes.thread = Derived({
			source: "threads",
			query: { type: "main" },
			get: (aui) => aui.threads.thread("main")
		});
	}
	if (!scopes.threadListItem && parent.threadListItem.source === null) scopes.threadListItem = Derived({
		source: "threads",
		query: { type: "main" },
		get: (aui) => aui.threads.item("main")
	});
	scopes.composer ??= Derived({
		source: "thread",
		query: {},
		get: (aui) => aui.thread.composer()
	});
	if (!scopes.modelContext && parent.modelContext.source === null) scopes.modelContext = ModelContext();
	if (!scopes.tools && parent.tools.source === null) scopes.tools = Tools({});
	if (!scopes.dataRenderers && parent.dataRenderers.source === null) scopes.dataRenderers = DataRenderers();
	if (!scopes.suggestions && parent.suggestions.source === null) scopes.suggestions = Derived({
		source: "thread",
		query: {},
		get: (aui) => aui.thread.suggestions()
	});
});
function _temp() {}
function _temp2(attachment) {
	return withKey(attachment.id, AttachmentResource({
		attachment,
		onRemove: _temp
	}));
}
function _temp3() {}
function _temp4() {}
function _temp5(entry_1) {
	return entry_1.submission;
}
function _temp6(part) {
	return part.type === "text";
}
function _temp7(part_0) {
	return part_0.text;
}
function _temp8(a_2) {
	return a_2.status.type !== "complete";
}
function _temp9(attachment_6) {
	return [attachment_6.id, attachment_6];
}
function _temp0(a_7) {
	return a_7.id;
}
function _temp1(attachment_11) {
	return [attachment_11.id, attachment_11];
}
function _temp10(result_0) {
	return result_0.status === "rejected";
}
function _temp11(error_0) {
	console.error("Failed to remove cancelled edit attachments", error_0);
}
function _temp12() {}
function _temp13() {}
function _temp14(message_1) {
	return `${message_1.id}|${message_1.role}`;
}
function _temp15(task) {
	return withKey(getTaskKey(task), TaskClient({ task }), [task]);
}
function _temp16() {}
function _temp17() {
	return {
		tools: {},
		config: {}
	};
}
function _temp18() {
	return { messages: [] };
}
function _temp19() {}
function _temp20() {}
function _temp21() {}
function _temp22() {}
function _temp23() {
	return 0;
}
function _temp24() {}
function _temp25() {
	return _temp24;
}
function _temp26() {}
function _temp27() {}
//#endregion
export { ExternalThread };
