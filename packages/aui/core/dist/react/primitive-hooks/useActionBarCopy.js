import { actionBarCopyDisabled } from "../../store/primitive-predicates.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useEffect, useInsertionEffect, useRef } from "@assistant-ui/tap/react-shim";
import { useAui, useAuiState } from "@assistant-ui/store";
//#region src/react/primitive-hooks/useActionBarCopy.ts
const useActionBarCopy = (t0) => {
	const $ = c(20);
	let t1;
	if ($[0] !== t0) {
		t1 = t0 === void 0 ? {} : t0;
		$[0] = t0;
		$[1] = t1;
	} else t1 = $[1];
	const { copiedDuration: t2, copyToClipboard } = t1;
	const copiedDuration = t2 === void 0 ? 3e3 : t2;
	const aui = useAui();
	const disabled = useAuiState(actionBarCopyDisabled);
	const messageId = useAuiState(_temp);
	const isCopied = useAuiState(_temp2);
	const isEditing = useAuiState(_temp3);
	const composerValue = useAuiState(_temp4);
	const copiedTimerRef = useRef(void 0);
	const copiedFeedbackTargetRef = useRef(void 0);
	const scopeGenerationRef = useRef(0);
	const committedMessageIdRef = useRef(messageId);
	let t3;
	let t4;
	if ($[2] !== messageId) {
		t3 = () => {
			committedMessageIdRef.current = messageId;
		};
		t4 = [messageId];
		$[2] = messageId;
		$[3] = t3;
		$[4] = t4;
	} else {
		t3 = $[3];
		t4 = $[4];
	}
	useInsertionEffect(t3, t4);
	let t5;
	if ($[5] === Symbol.for("react.memo_cache_sentinel")) {
		t5 = () => () => {
			scopeGenerationRef.current = scopeGenerationRef.current + 1;
			if (copiedTimerRef.current === void 0) return;
			clearTimeout(copiedTimerRef.current);
			copiedTimerRef.current = void 0;
			copiedFeedbackTargetRef.current?.(false);
			copiedFeedbackTargetRef.current = void 0;
		};
		$[5] = t5;
	} else t5 = $[5];
	let t6;
	if ($[6] !== aui || $[7] !== messageId) {
		t6 = [aui, messageId];
		$[6] = aui;
		$[7] = messageId;
		$[8] = t6;
	} else t6 = $[8];
	useEffect(t5, t6);
	let t7;
	if ($[9] !== aui || $[10] !== composerValue || $[11] !== copiedDuration || $[12] !== copyToClipboard || $[13] !== isEditing || $[14] !== messageId) {
		t7 = () => {
			if (!copyToClipboard) return;
			const valueToCopy = isEditing ? composerValue : aui.message.getCopyText();
			if (!valueToCopy) return;
			const scopeGeneration = scopeGenerationRef.current;
			const copiedMessageId = messageId;
			const setCopyFeedback = aui.message.setIsCopied;
			let write;
			try {
				write = copyToClipboard(valueToCopy);
			} catch {
				return;
			}
			Promise.resolve(write).then(() => {
				if (scopeGeneration !== scopeGenerationRef.current || copiedMessageId !== committedMessageIdRef.current) return;
				if (copiedTimerRef.current !== void 0) clearTimeout(copiedTimerRef.current);
				copiedFeedbackTargetRef.current = setCopyFeedback;
				setCopyFeedback(true);
				copiedTimerRef.current = setTimeout(() => {
					copiedTimerRef.current = void 0;
					if (copiedMessageId !== committedMessageIdRef.current) {
						setCopyFeedback(false);
						copiedFeedbackTargetRef.current = void 0;
						return;
					}
					setCopyFeedback(false);
					copiedFeedbackTargetRef.current = void 0;
				}, copiedDuration);
			}, _temp5);
		};
		$[9] = aui;
		$[10] = composerValue;
		$[11] = copiedDuration;
		$[12] = copyToClipboard;
		$[13] = isEditing;
		$[14] = messageId;
		$[15] = t7;
	} else t7 = $[15];
	const copy = t7;
	const t8 = disabled || !copyToClipboard;
	let t9;
	if ($[16] !== copy || $[17] !== isCopied || $[18] !== t8) {
		t9 = {
			copy,
			disabled: t8,
			isCopied
		};
		$[16] = copy;
		$[17] = isCopied;
		$[18] = t8;
		$[19] = t9;
	} else t9 = $[19];
	return t9;
};
function _temp(s) {
	return s.message.id;
}
function _temp2(s_0) {
	return s_0.message.isCopied;
}
function _temp3(s_1) {
	return s_1.composer.isEditing;
}
function _temp4(s_2) {
	return s_2.composer.text;
}
function _temp5() {}
//#endregion
export { useActionBarCopy };
