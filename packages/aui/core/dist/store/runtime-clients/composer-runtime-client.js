import { runCleanups } from "../../subscribable/subscribable.js";
import { useSubscribable } from "./useSubscribable.js";
import { AttachmentRuntimeClient } from "./attachment-runtime-client.js";
import { useAssistantEmit, useClientLookup } from "@assistant-ui/store/client";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useEffect, useRef } from "@assistant-ui/tap/react-shim";
import { resource, useResource, withKey } from "@assistant-ui/tap";
//#region src/store/runtime-clients/composer-runtime-client.ts
const useComposerAttachmentClientByIndex = (t0) => {
	const $ = c(5);
	const { runtime, index } = t0;
	let t1;
	if ($[0] !== index || $[1] !== runtime) {
		t1 = runtime.getAttachmentByIndex(index);
		$[0] = index;
		$[1] = runtime;
		$[2] = t1;
	} else t1 = $[2];
	const attachmentRuntime = t1;
	let t2;
	if ($[3] !== attachmentRuntime) {
		t2 = AttachmentRuntimeClient({ runtime: attachmentRuntime });
		$[3] = attachmentRuntime;
		$[4] = t2;
	} else t2 = $[4];
	return useResource(t2);
};
const ComposerAttachmentClientByIndex = resource(useComposerAttachmentClientByIndex);
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
const useComposerClient = (t0) => {
	const $ = c(65);
	const { threadIdRef, messageIdRef, runtime, isSuggestion } = t0;
	const runtimeState = useSubscribable(runtime);
	const emit = useAssistantEmit();
	const pendingSuggestion = useRef(false);
	let t1;
	let t2;
	if ($[0] !== emit || $[1] !== messageIdRef || $[2] !== runtime || $[3] !== threadIdRef) {
		t1 = () => {
			const unsubscribers = [];
			const sendUnsubscribe = runtime.unstable_on("send", (payload) => {
				const suggestion = pendingSuggestion.current;
				pendingSuggestion.current = false;
				emit("composer.send", {
					threadId: threadIdRef.current,
					...messageIdRef && { messageId: messageIdRef.current },
					chars: payload.chars,
					attachments: payload.attachments,
					...suggestion ? { suggestion: true } : void 0
				});
			});
			unsubscribers.push(sendUnsubscribe);
			const attachmentUnsubscribe = runtime.unstable_on("attachmentAdd", (payload_0) => {
				emit("composer.attachmentAdd", {
					threadId: threadIdRef.current,
					...messageIdRef && { messageId: messageIdRef.current },
					...payload_0.contentType ? { contentType: payload_0.contentType } : void 0
				});
			});
			unsubscribers.push(attachmentUnsubscribe);
			unsubscribers.push(runtime.unstable_on("attachmentAddError", (payload_1) => {
				emit("composer.attachmentAddError", {
					threadId: threadIdRef.current,
					...messageIdRef && { messageId: messageIdRef.current },
					...payload_1.attachmentId && { attachmentId: payload_1.attachmentId },
					reason: payload_1.reason,
					message: payload_1.message,
					...payload_1.contentType ? { contentType: payload_1.contentType } : void 0
				});
			}));
			return () => runCleanups(unsubscribers);
		};
		t2 = [
			runtime,
			emit,
			threadIdRef,
			messageIdRef
		];
		$[0] = emit;
		$[1] = messageIdRef;
		$[2] = runtime;
		$[3] = threadIdRef;
		$[4] = t1;
		$[5] = t2;
	} else {
		t1 = $[4];
		t2 = $[5];
	}
	useEffect(t1, t2);
	let t3;
	if ($[6] !== runtime || $[7] !== runtimeState.attachments) {
		let t4;
		if ($[9] !== runtime) {
			t4 = (attachment, idx) => withKey(attachment.id, ComposerAttachmentClientByIndex({
				runtime,
				index: idx
			}), [runtime, idx]);
			$[9] = runtime;
			$[10] = t4;
		} else t4 = $[10];
		t3 = runtimeState.attachments.map(t4);
		$[6] = runtime;
		$[7] = runtimeState.attachments;
		$[8] = t3;
	} else t3 = $[8];
	const attachments = useClientLookup(t3);
	const queue = runtimeState.queue;
	let t4;
	if ($[11] !== queue || $[12] !== runtime) {
		let t5;
		if ($[14] !== runtime) {
			t5 = (item) => withKey(item.id, QueueItemClient({
				item,
				onMove: (placement) => runtime.moveQueueItem(item.id, placement),
				onEdit: (message) => runtime.editQueueItem(item.id, message),
				onRemove: () => runtime.removeQueueItem(item.id)
			}));
			$[14] = runtime;
			$[15] = t5;
		} else t5 = $[15];
		t4 = queue.map(t5);
		$[11] = queue;
		$[12] = runtime;
		$[13] = t4;
	} else t4 = $[13];
	const queueItems = useClientLookup(t4);
	const t5 = runtimeState.type ?? "thread";
	let t6;
	if ($[16] !== attachments.state || $[17] !== queue || $[18] !== runtimeState.attachmentAccept || $[19] !== runtimeState.canCancel || $[20] !== runtimeState.canSend || $[21] !== runtimeState.dictation || $[22] !== runtimeState.inTransit || $[23] !== runtimeState.isEditing || $[24] !== runtimeState.isEmpty || $[25] !== runtimeState.quote || $[26] !== runtimeState.role || $[27] !== runtimeState.runConfig || $[28] !== runtimeState.submission || $[29] !== runtimeState.text || $[30] !== t5) {
		t6 = {
			text: runtimeState.text,
			role: runtimeState.role,
			attachments: attachments.state,
			runConfig: runtimeState.runConfig,
			isEditing: runtimeState.isEditing,
			canCancel: runtimeState.canCancel,
			canSend: runtimeState.canSend,
			attachmentAccept: runtimeState.attachmentAccept,
			isEmpty: runtimeState.isEmpty,
			type: t5,
			dictation: runtimeState.dictation,
			quote: runtimeState.quote,
			queue,
			submission: runtimeState.submission,
			inTransit: runtimeState.inTransit
		};
		$[16] = attachments.state;
		$[17] = queue;
		$[18] = runtimeState.attachmentAccept;
		$[19] = runtimeState.canCancel;
		$[20] = runtimeState.canSend;
		$[21] = runtimeState.dictation;
		$[22] = runtimeState.inTransit;
		$[23] = runtimeState.isEditing;
		$[24] = runtimeState.isEmpty;
		$[25] = runtimeState.quote;
		$[26] = runtimeState.role;
		$[27] = runtimeState.runConfig;
		$[28] = runtimeState.submission;
		$[29] = runtimeState.text;
		$[30] = t5;
		$[31] = t6;
	} else t6 = $[31];
	const state = t6;
	let t7;
	if ($[32] !== state) {
		t7 = () => state;
		$[32] = state;
		$[33] = t7;
	} else t7 = $[33];
	let t8;
	if ($[34] !== isSuggestion || $[35] !== runtime) {
		t8 = (options) => {
			const state_0 = runtime.getState();
			pendingSuggestion.current = state_0.canSend && (isSuggestion?.(state_0.text) ?? false);
			runtime.send(options);
		};
		$[34] = isSuggestion;
		$[35] = runtime;
		$[36] = t8;
	} else t8 = $[36];
	let t9;
	if ($[37] !== emit || $[38] !== messageIdRef || $[39] !== runtime || $[40] !== threadIdRef) {
		t9 = () => {
			if (!messageIdRef && runtime.getState().canCancel) emit("composer.cancel", { threadId: threadIdRef.current });
			runtime.cancel();
		};
		$[37] = emit;
		$[38] = messageIdRef;
		$[39] = runtime;
		$[40] = threadIdRef;
		$[41] = t9;
	} else t9 = $[41];
	const t10 = runtime.beginEdit ?? _temp;
	let t11;
	if ($[42] !== attachments) {
		t11 = (selector) => {
			if ("id" in selector) return attachments.get({ key: selector.id });
			else return attachments.get(selector);
		};
		$[42] = attachments;
		$[43] = t11;
	} else t11 = $[43];
	let t12;
	if ($[44] !== queueItems) {
		t12 = (selector_0) => {
			if ("id" in selector_0) return queueItems.get({ key: selector_0.id });
			else return queueItems.get(selector_0);
		};
		$[44] = queueItems;
		$[45] = t12;
	} else t12 = $[45];
	let t13;
	if ($[46] !== runtime) {
		t13 = () => runtime;
		$[46] = runtime;
		$[47] = t13;
	} else t13 = $[47];
	let t14;
	if ($[48] !== runtime.addAttachment || $[49] !== runtime.clearAttachments || $[50] !== runtime.reset || $[51] !== runtime.setQuote || $[52] !== runtime.setRole || $[53] !== runtime.setRunConfig || $[54] !== runtime.setText || $[55] !== runtime.startDictation || $[56] !== runtime.stopDictation || $[57] !== t10 || $[58] !== t11 || $[59] !== t12 || $[60] !== t13 || $[61] !== t7 || $[62] !== t8 || $[63] !== t9) {
		t14 = {
			getState: t7,
			setText: runtime.setText,
			setRole: runtime.setRole,
			setRunConfig: runtime.setRunConfig,
			addAttachment: runtime.addAttachment,
			reset: runtime.reset,
			clearAttachments: runtime.clearAttachments,
			send: t8,
			cancel: t9,
			beginEdit: t10,
			startDictation: runtime.startDictation,
			stopDictation: runtime.stopDictation,
			setQuote: runtime.setQuote,
			attachment: t11,
			queueItem: t12,
			__internal_getRuntime: t13
		};
		$[48] = runtime.addAttachment;
		$[49] = runtime.clearAttachments;
		$[50] = runtime.reset;
		$[51] = runtime.setQuote;
		$[52] = runtime.setRole;
		$[53] = runtime.setRunConfig;
		$[54] = runtime.setText;
		$[55] = runtime.startDictation;
		$[56] = runtime.stopDictation;
		$[57] = t10;
		$[58] = t11;
		$[59] = t12;
		$[60] = t13;
		$[61] = t7;
		$[62] = t8;
		$[63] = t9;
		$[64] = t14;
	} else t14 = $[64];
	return t14;
};
const ComposerClient = resource(useComposerClient);
function _temp() {
	throw new Error("beginEdit is not supported in this runtime");
}
//#endregion
export { ComposerClient };
