"use client";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useAuiState } from "@assistant-ui/store";
//#region src/primitives/message/MessageIf.ts
const useMessageIf = (props) => {
	const $ = c(12);
	let t0;
	if ($[0] !== props.assistant || $[1] !== props.copied || $[2] !== props.hasAttachments || $[3] !== props.hasBranches || $[4] !== props.hasContent || $[5] !== props.last || $[6] !== props.lastOrHover || $[7] !== props.speaking || $[8] !== props.submittedFeedback || $[9] !== props.system || $[10] !== props.user) {
		t0 = (s) => {
			const { role, attachments, parts, branchCount, isLast, speech, isCopied, isHovering } = s.message;
			if (props.hasBranches === true && branchCount < 2) return false;
			if (props.user === true && role !== "user") return false;
			if (props.user === false && role === "user") return false;
			if (props.assistant === true && role !== "assistant") return false;
			if (props.assistant === false && role === "assistant") return false;
			if (props.system === true && role !== "system") return false;
			if (props.system === false && role === "system") return false;
			if (props.lastOrHover === true && !isHovering && !isLast) return false;
			if (props.last !== void 0 && props.last !== isLast) return false;
			if (props.copied === true && !isCopied) return false;
			if (props.copied === false && isCopied) return false;
			if (props.speaking === true && speech == null) return false;
			if (props.speaking === false && speech != null) return false;
			if (props.hasAttachments === true && (role !== "user" || !attachments?.length)) return false;
			if (props.hasAttachments === false && role === "user" && attachments?.length) return false;
			if (props.hasContent === true && parts.length === 0) return false;
			if (props.hasContent === false && parts.length > 0) return false;
			if (props.submittedFeedback !== void 0 && (s.message.metadata.submittedFeedback?.type ?? null) !== props.submittedFeedback) return false;
			return true;
		};
		$[0] = props.assistant;
		$[1] = props.copied;
		$[2] = props.hasAttachments;
		$[3] = props.hasBranches;
		$[4] = props.hasContent;
		$[5] = props.last;
		$[6] = props.lastOrHover;
		$[7] = props.speaking;
		$[8] = props.submittedFeedback;
		$[9] = props.system;
		$[10] = props.user;
		$[11] = t0;
	} else t0 = $[11];
	return useAuiState(t0);
};
/**
* @deprecated Use `<AuiIf condition={(s) => s.message...} />` instead.
*/
const MessagePrimitiveIf = (t0) => {
	const $ = c(3);
	let children;
	let query;
	if ($[0] !== t0) {
		({children, ...query} = t0);
		$[0] = t0;
		$[1] = children;
		$[2] = query;
	} else {
		children = $[1];
		query = $[2];
	}
	return useMessageIf(query) ? children : null;
};
MessagePrimitiveIf.displayName = "MessagePrimitive.If";
//#endregion
export { MessagePrimitiveIf };
