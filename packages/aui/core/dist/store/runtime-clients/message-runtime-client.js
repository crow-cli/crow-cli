import { getMessagePartKeys } from "../../utils/getMessagePartKeys.js";
import { useSubscribable } from "./useSubscribable.js";
import { AttachmentRuntimeClient } from "./attachment-runtime-client.js";
import { MessagePartClient } from "./message-part-runtime-client.js";
import { ComposerClient } from "./composer-runtime-client.js";
import { liveRef } from "./liveRef.js";
import { useAssistantEmit, useClientLookup, useClientResource } from "@assistant-ui/store/client";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useEffect, useRef, useState } from "@assistant-ui/tap/react-shim";
import { resource, useResource, withKey } from "@assistant-ui/tap";
//#region src/store/runtime-clients/message-runtime-client.ts
const useMessageAttachmentClientByIndex = (t0) => {
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
const MessageAttachmentClientByIndex = resource(useMessageAttachmentClientByIndex);
const useMessagePartByIndex = (t0) => {
	const $ = c(5);
	const { runtime, index } = t0;
	let t1;
	if ($[0] !== index || $[1] !== runtime) {
		t1 = runtime.getMessagePartByIndex(index);
		$[0] = index;
		$[1] = runtime;
		$[2] = t1;
	} else t1 = $[2];
	const partRuntime = t1;
	let t2;
	if ($[3] !== partRuntime) {
		t2 = MessagePartClient({ runtime: partRuntime });
		$[3] = partRuntime;
		$[4] = t2;
	} else t2 = $[4];
	return useResource(t2);
};
const MessagePartByIndex = resource(useMessagePartByIndex);
const useMessageClient = (t0) => {
	const $ = c(78);
	const { runtime, threadIdRef, threadId, isLast } = t0;
	const runtimeState = useSubscribable(runtime);
	const emit = useAssistantEmit();
	const [isCopiedState, setIsCopied] = useState(false);
	const [isHoveringState, setIsHovering] = useState(false);
	let t1;
	if ($[0] !== runtime) {
		t1 = liveRef(() => runtime.getState().id);
		$[0] = runtime;
		$[1] = t1;
	} else t1 = $[1];
	const messageIdRef = t1;
	const previousStatus = useRef(runtimeState.status);
	let t2;
	if ($[2] !== emit || $[3] !== runtime || $[4] !== threadId) {
		t2 = (event) => {
			emit(event, {
				threadId,
				messageId: runtime.getState().id
			});
		};
		$[2] = emit;
		$[3] = runtime;
		$[4] = threadId;
		$[5] = t2;
	} else t2 = $[5];
	const emitMessageEvent = t2;
	let t3;
	let t4;
	if ($[6] !== emit || $[7] !== runtimeState.id || $[8] !== runtimeState.status || $[9] !== threadId) {
		t3 = () => {
			const status = runtimeState.status;
			const previous = previousStatus.current;
			previousStatus.current = status;
			if (status?.type === "incomplete" && status.reason === "error" && (previous?.type !== "incomplete" || previous.reason !== "error")) emit("message.error", {
				threadId,
				messageId: runtimeState.id,
				reason: "error"
			});
		};
		t4 = [
			runtimeState.status,
			runtimeState.id,
			emit,
			threadId
		];
		$[6] = emit;
		$[7] = runtimeState.id;
		$[8] = runtimeState.status;
		$[9] = threadId;
		$[10] = t3;
		$[11] = t4;
	} else {
		t3 = $[10];
		t4 = $[11];
	}
	useEffect(t3, t4);
	let t5;
	if ($[12] !== messageIdRef || $[13] !== runtime.composer || $[14] !== threadIdRef) {
		t5 = ComposerClient({
			runtime: runtime.composer,
			threadIdRef,
			messageIdRef
		});
		$[12] = messageIdRef;
		$[13] = runtime.composer;
		$[14] = threadIdRef;
		$[15] = t5;
	} else t5 = $[15];
	const composer = useClientResource(t5);
	let t6;
	if ($[16] !== runtime || $[17] !== runtimeState.content) {
		let t7;
		if ($[19] !== runtime) {
			t7 = (key, idx) => withKey(key, MessagePartByIndex({
				runtime,
				index: idx
			}), [runtime, idx]);
			$[19] = runtime;
			$[20] = t7;
		} else t7 = $[20];
		t6 = getMessagePartKeys(runtimeState.content).map(t7);
		$[16] = runtime;
		$[17] = runtimeState.content;
		$[18] = t6;
	} else t6 = $[18];
	const parts = useClientLookup(t6);
	let t7;
	if ($[21] !== runtimeState.attachments) {
		t7 = runtimeState.attachments ?? [];
		$[21] = runtimeState.attachments;
		$[22] = t7;
	} else t7 = $[22];
	let t8;
	if ($[23] !== runtime || $[24] !== t7) {
		let t9;
		if ($[26] !== runtime) {
			t9 = (attachment, idx_0) => withKey(attachment.id, MessageAttachmentClientByIndex({
				runtime,
				index: idx_0
			}), [runtime, idx_0]);
			$[26] = runtime;
			$[27] = t9;
		} else t9 = $[27];
		t8 = t7.map(t9);
		$[23] = runtime;
		$[24] = t7;
		$[25] = t8;
	} else t8 = $[25];
	const attachments = useClientLookup(t8);
	const t9 = runtimeState;
	let t10;
	if ($[28] !== isLast) {
		t10 = isLast === false ? { isLast } : {};
		$[28] = isLast;
		$[29] = t10;
	} else t10 = $[29];
	let t11;
	if ($[30] !== composer.state || $[31] !== isCopiedState || $[32] !== isHoveringState || $[33] !== parts.state || $[34] !== t10 || $[35] !== t9) {
		t11 = {
			...t9,
			...t10,
			parts: parts.state,
			composer: composer.state,
			isCopied: isCopiedState,
			isHovering: isHoveringState
		};
		$[30] = composer.state;
		$[31] = isCopiedState;
		$[32] = isHoveringState;
		$[33] = parts.state;
		$[34] = t10;
		$[35] = t9;
		$[36] = t11;
	} else t11 = $[36];
	const state = t11;
	let t12;
	if ($[37] !== state) {
		t12 = () => state;
		$[37] = state;
		$[38] = t12;
	} else t12 = $[38];
	let t13;
	if ($[39] !== composer.methods) {
		t13 = () => composer.methods;
		$[39] = composer.methods;
		$[40] = t13;
	} else t13 = $[40];
	let t14;
	if ($[41] !== runtime) {
		t14 = () => runtime.delete();
		$[41] = runtime;
		$[42] = t14;
	} else t14 = $[42];
	let t15;
	let t16;
	if ($[43] !== emitMessageEvent || $[44] !== runtime) {
		t15 = (config) => {
			emitMessageEvent("message.reload");
			return runtime.reload(config);
		};
		t16 = () => {
			emitMessageEvent("message.speak");
			return runtime.speak();
		};
		$[43] = emitMessageEvent;
		$[44] = runtime;
		$[45] = t15;
		$[46] = t16;
	} else {
		t15 = $[45];
		t16 = $[46];
	}
	let t17;
	let t18;
	if ($[47] !== runtime) {
		t17 = () => runtime.stopSpeaking();
		t18 = (feedback) => runtime.submitFeedback(feedback);
		$[47] = runtime;
		$[48] = t17;
		$[49] = t18;
	} else {
		t17 = $[48];
		t18 = $[49];
	}
	let t19;
	if ($[50] !== emitMessageEvent || $[51] !== runtime) {
		t19 = (options) => {
			emitMessageEvent("message.branchSwitched");
			return runtime.switchToBranch(options);
		};
		$[50] = emitMessageEvent;
		$[51] = runtime;
		$[52] = t19;
	} else t19 = $[52];
	let t20;
	if ($[53] !== runtime) {
		t20 = () => runtime.unstable_getCopyText();
		$[53] = runtime;
		$[54] = t20;
	} else t20 = $[54];
	let t21;
	if ($[55] !== parts || $[56] !== runtimeState.content) {
		t21 = (selector) => {
			if ("index" in selector) return parts.get({ index: selector.index });
			else {
				const index = runtimeState.content.findIndex((part) => part.type === "tool-call" && part.toolCallId === selector.toolCallId);
				return parts.get({ index });
			}
		};
		$[55] = parts;
		$[56] = runtimeState.content;
		$[57] = t21;
	} else t21 = $[57];
	let t22;
	if ($[58] !== attachments) {
		t22 = (selector_0) => {
			if ("id" in selector_0) return attachments.get({ key: selector_0.id });
			else return attachments.get(selector_0);
		};
		$[58] = attachments;
		$[59] = t22;
	} else t22 = $[59];
	let t23;
	if ($[60] !== emitMessageEvent) {
		t23 = (value) => {
			if (value) emitMessageEvent("message.copied");
			setIsCopied(value);
		};
		$[60] = emitMessageEvent;
		$[61] = t23;
	} else t23 = $[61];
	let t24;
	if ($[62] !== runtime) {
		t24 = () => runtime;
		$[62] = runtime;
		$[63] = t24;
	} else t24 = $[63];
	let t25;
	if ($[64] !== t12 || $[65] !== t13 || $[66] !== t14 || $[67] !== t15 || $[68] !== t16 || $[69] !== t17 || $[70] !== t18 || $[71] !== t19 || $[72] !== t20 || $[73] !== t21 || $[74] !== t22 || $[75] !== t23 || $[76] !== t24) {
		t25 = {
			getState: t12,
			composer: t13,
			delete: t14,
			reload: t15,
			speak: t16,
			stopSpeaking: t17,
			submitFeedback: t18,
			switchToBranch: t19,
			getCopyText: t20,
			part: t21,
			attachment: t22,
			setIsCopied: t23,
			setIsHovering,
			__internal_getRuntime: t24
		};
		$[64] = t12;
		$[65] = t13;
		$[66] = t14;
		$[67] = t15;
		$[68] = t16;
		$[69] = t17;
		$[70] = t18;
		$[71] = t19;
		$[72] = t20;
		$[73] = t21;
		$[74] = t22;
		$[75] = t23;
		$[76] = t24;
		$[77] = t25;
	} else t25 = $[77];
	return t25;
};
const MessageClient = resource(useMessageClient);
//#endregion
export { MessageClient };
