import { getThreadMessageText } from "../../utils/text.js";
import { COMPLETE_STATUS, normalizePartStatus } from "../../utils/normalizePartStatus.js";
import { getMessagePartKeys } from "../../utils/getMessagePartKeys.js";
import { NoOpComposerClient } from "./no-op-composer-client.js";
import { useClientLookup, useClientResource } from "@assistant-ui/store/client";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useState } from "@assistant-ui/tap/react-shim";
import { resource, withKey } from "@assistant-ui/tap";
//#region src/store/clients/thread-message-client.ts
const useThreadMessagePartClient = (t0) => {
	const $ = c(8);
	const { part, isMessageRunning } = t0;
	let t1;
	if ($[0] !== isMessageRunning || $[1] !== part) {
		t1 = isMessageRunning ? normalizePartStatus(part) ?? COMPLETE_STATUS : COMPLETE_STATUS;
		$[0] = isMessageRunning;
		$[1] = part;
		$[2] = t1;
	} else t1 = $[2];
	let t2;
	if ($[3] !== part || $[4] !== t1) {
		t2 = {
			...part,
			status: t1
		};
		$[3] = part;
		$[4] = t1;
		$[5] = t2;
	} else t2 = $[5];
	const state = t2;
	let t3;
	if ($[6] !== state) {
		t3 = {
			getState: () => state,
			addToolResult: _temp,
			resumeToolCall: _temp2,
			respondToToolApproval: _temp3,
			unstable_recordInteraction: _temp4
		};
		$[6] = state;
		$[7] = t3;
	} else t3 = $[7];
	return t3;
};
const ThreadMessagePartClient = resource(useThreadMessagePartClient);
const useThreadMessageAttachmentClient = ({ attachment }) => {
	return {
		getState: () => attachment,
		remove: () => {
			throw new Error("Not supported");
		}
	};
};
const ThreadMessageAttachmentClient = resource(useThreadMessageAttachmentClient);
const useThreadMessageClient = (t0) => {
	const $ = c(38);
	const { message, index, isLast: t1, branchNumber: t2, branchCount: t3, submission } = t0;
	const isLast = t1 === void 0 ? true : t1;
	const branchNumber = t2 === void 0 ? 1 : t2;
	const branchCount = t3 === void 0 ? 1 : t3;
	const [isCopiedState, setIsCopied] = useState(false);
	const [isHoveringState, setIsHovering] = useState(false);
	const isMessageRunning = message.role === "assistant" && message.status.type === "running";
	let t4;
	let t5;
	if ($[0] !== isMessageRunning || $[1] !== message.content) {
		const partKeys = getMessagePartKeys(message.content);
		t4 = useClientLookup;
		t5 = message.content.map((part, idx) => withKey(partKeys[idx], ThreadMessagePartClient({
			part,
			isMessageRunning
		}), [part, isMessageRunning]));
		$[0] = isMessageRunning;
		$[1] = message.content;
		$[2] = t4;
		$[3] = t5;
	} else {
		t4 = $[2];
		t5 = $[3];
	}
	const parts = t4(t5);
	let t6;
	if ($[4] !== message.attachments || $[5] !== submission?.attachments) {
		t6 = submission?.attachments ?? message.attachments ?? [];
		$[4] = message.attachments;
		$[5] = submission?.attachments;
		$[6] = t6;
	} else t6 = $[6];
	let t7;
	if ($[7] !== t6) {
		t7 = t6.map(_temp5);
		$[7] = t6;
		$[8] = t7;
	} else t7 = $[8];
	const attachments = useClientLookup(t7);
	let t8;
	if ($[9] === Symbol.for("react.memo_cache_sentinel")) {
		t8 = NoOpComposerClient({ type: "edit" });
		$[9] = t8;
	} else t8 = $[9];
	const composer = useClientResource(t8);
	const composerState = composer.state;
	let t9;
	if ($[10] !== branchCount || $[11] !== branchNumber || $[12] !== composerState || $[13] !== index || $[14] !== isCopiedState || $[15] !== isHoveringState || $[16] !== isLast || $[17] !== message || $[18] !== parts.state || $[19] !== submission) {
		t9 = {
			...message,
			parts: parts.state,
			composer: composerState,
			parentId: null,
			index,
			isLast,
			branchNumber,
			branchCount,
			speech: void 0,
			isCopied: isCopiedState,
			isHovering: isHoveringState,
			submission
		};
		$[10] = branchCount;
		$[11] = branchNumber;
		$[12] = composerState;
		$[13] = index;
		$[14] = isCopiedState;
		$[15] = isHoveringState;
		$[16] = isLast;
		$[17] = message;
		$[18] = parts.state;
		$[19] = submission;
		$[20] = t9;
	} else t9 = $[20];
	const state = t9;
	let t10;
	if ($[21] !== state) {
		t10 = () => state;
		$[21] = state;
		$[22] = t10;
	} else t10 = $[22];
	let t11;
	if ($[23] !== composer.methods) {
		t11 = () => composer.methods;
		$[23] = composer.methods;
		$[24] = t11;
	} else t11 = $[24];
	let t12;
	if ($[25] !== message.content || $[26] !== parts) {
		t12 = (selector) => {
			if ("index" in selector) return parts.get({ index: selector.index });
			else return parts.get({ index: message.content.findIndex((part_0) => part_0.type === "tool-call" && part_0.toolCallId === selector.toolCallId) });
		};
		$[25] = message.content;
		$[26] = parts;
		$[27] = t12;
	} else t12 = $[27];
	let t13;
	if ($[28] !== attachments) {
		t13 = (selector_0) => {
			if ("id" in selector_0) return attachments.get({ key: selector_0.id });
			else return attachments.get(selector_0);
		};
		$[28] = attachments;
		$[29] = t13;
	} else t13 = $[29];
	let t14;
	if ($[30] !== message) {
		t14 = () => getThreadMessageText(message);
		$[30] = message;
		$[31] = t14;
	} else t14 = $[31];
	let t15;
	if ($[32] !== t10 || $[33] !== t11 || $[34] !== t12 || $[35] !== t13 || $[36] !== t14) {
		t15 = {
			getState: t10,
			composer: t11,
			part: t12,
			attachment: t13,
			delete: _temp6,
			reload: _temp7,
			speak: _temp8,
			stopSpeaking: _temp9,
			submitFeedback: _temp0,
			switchToBranch: _temp1,
			getCopyText: t14,
			setIsCopied,
			setIsHovering
		};
		$[32] = t10;
		$[33] = t11;
		$[34] = t12;
		$[35] = t13;
		$[36] = t14;
		$[37] = t15;
	} else t15 = $[37];
	return t15;
};
const ThreadMessageClient = resource(useThreadMessageClient);
function _temp() {
	throw new Error("Not supported");
}
function _temp2() {
	throw new Error("Not supported");
}
function _temp3() {
	throw new Error("Not supported");
}
async function _temp4() {}
function _temp5(attachment) {
	return withKey(attachment.id, ThreadMessageAttachmentClient({ attachment }), [attachment]);
}
function _temp6() {
	throw new Error("Not supported in ThreadMessageProvider");
}
function _temp7() {
	throw new Error("Not supported in ThreadMessageProvider");
}
function _temp8() {
	throw new Error("Not supported in ThreadMessageProvider");
}
function _temp9() {
	throw new Error("Not supported in ThreadMessageProvider");
}
function _temp0() {
	throw new Error("Not supported in ThreadMessageProvider");
}
function _temp1() {
	throw new Error("Not supported in ThreadMessageProvider");
}
//#endregion
export { ThreadMessageClient };
