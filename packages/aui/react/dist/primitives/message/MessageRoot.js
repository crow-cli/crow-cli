"use client";
import { useThreadViewport, useThreadViewportStore } from "../../context/react/ThreadViewportContext.js";
import { Primitive as Primitive$1 } from "../../utils/Primitive.js";
import { useManagedRef } from "../../utils/hooks/useManagedRef.js";
import { parseCssLength } from "../thread/topAnchor/topAnchorUtils.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { forwardRef } from "@assistant-ui/tap/react-shim";
import { useAui, useAuiState } from "@assistant-ui/store";
import { jsx } from "react/jsx-runtime";
import { useComposedRefs } from "radix-ui/internal";
//#region src/primitives/message/MessageRoot.tsx
const useIsHoveringRef = () => {
	const $ = c(4);
	const aui = useAui();
	let t0;
	if ($[0] !== aui.message) {
		t0 = () => aui.message;
		$[0] = aui.message;
		$[1] = t0;
	} else t0 = $[1];
	const message = useAuiState(t0);
	let t1;
	if ($[2] !== message) {
		t1 = (el) => {
			let active = true;
			const handleMouseEnter = () => {
				message.setIsHovering(true);
			};
			const handleMouseLeave = () => {
				message.setIsHovering(false);
			};
			el.addEventListener("mouseenter", handleMouseEnter);
			el.addEventListener("mouseleave", handleMouseLeave);
			if (el.matches(":hover")) queueMicrotask(() => {
				if (active) message.setIsHovering(true);
			});
			return () => {
				active = false;
				el.removeEventListener("mouseenter", handleMouseEnter);
				el.removeEventListener("mouseleave", handleMouseLeave);
				message.setIsHovering(false);
			};
		};
		$[2] = message;
		$[3] = t1;
	} else t1 = $[3];
	return useManagedRef(t1);
};
const useIsTopAnchorUser = () => {
	const $ = c(2);
	const activeAnchorId = useThreadViewport(_temp);
	let t0;
	if ($[0] !== activeAnchorId) {
		t0 = (s_0) => s_0.message.role === "user" && s_0.message.index > 0 && s_0.message.index === s_0.thread.messages.length - 2 && s_0.thread.messages.at(-1)?.role === "assistant" && (s_0.message.id === activeAnchorId || s_0.thread.isRunning);
		$[0] = activeAnchorId;
		$[1] = t0;
	} else t0 = $[1];
	return useAuiState(t0);
};
const useIsTopAnchorTarget = () => {
	const $ = c(2);
	const activeTargetId = useThreadViewport(_temp2);
	let t0;
	if ($[0] !== activeTargetId) {
		t0 = (s_0) => s_0.message.isLast && s_0.message.role === "assistant" && s_0.message.index >= 1 && s_0.thread.messages.at(s_0.message.index - 1)?.role === "user" && (s_0.message.id === activeTargetId || s_0.thread.isRunning);
		$[0] = activeTargetId;
		$[1] = t0;
	} else t0 = $[1];
	return useAuiState(t0);
};
const useTopAnchorUserRef = (active, threadViewportStore) => {
	const $ = c(3);
	let t0;
	if ($[0] !== active || $[1] !== threadViewportStore) {
		t0 = (el) => {
			if (!active) return;
			return threadViewportStore.getState().registerAnchorElement(el);
		};
		$[0] = active;
		$[1] = threadViewportStore;
		$[2] = t0;
	} else t0 = $[2];
	return useManagedRef(t0);
};
const useTopAnchorTargetRef = (t0) => {
	const $ = c(3);
	const { active, threadViewportStore } = t0;
	let t1;
	if ($[0] !== active || $[1] !== threadViewportStore) {
		t1 = (el) => {
			if (!active) return;
			const state = threadViewportStore.getState();
			const clamp = state.topAnchorMessageClamp;
			return state.registerAnchorTargetElement(el, {
				tallerThan: parseCssLength(clamp.tallerThan, el),
				visibleHeight: parseCssLength(clamp.visibleHeight, el)
			});
		};
		$[0] = active;
		$[1] = threadViewportStore;
		$[2] = t1;
	} else t1 = $[2];
	return useManagedRef(t1);
};
const MessagePrimitiveRootDefault = (t0) => {
	const $ = c(7);
	let forwardedRef;
	let props;
	if ($[0] !== t0) {
		({forwardedRef, ...props} = t0);
		$[0] = t0;
		$[1] = forwardedRef;
		$[2] = props;
	} else {
		forwardedRef = $[1];
		props = $[2];
	}
	const isHoveringRef = useIsHoveringRef();
	const ref = useComposedRefs(forwardedRef, isHoveringRef);
	const messageId = useAuiState(_temp3);
	let t1;
	if ($[3] !== messageId || $[4] !== props || $[5] !== ref) {
		t1 = /* @__PURE__ */ jsx(Primitive$1.div, {
			...props,
			ref,
			"data-message-id": messageId
		});
		$[3] = messageId;
		$[4] = props;
		$[5] = ref;
		$[6] = t1;
	} else t1 = $[6];
	return t1;
};
const MessagePrimitiveRootTopAnchor = (t0) => {
	const $ = c(13);
	let forwardedRef;
	let props;
	let threadViewportStore;
	if ($[0] !== t0) {
		({forwardedRef, threadViewportStore, ...props} = t0);
		$[0] = t0;
		$[1] = forwardedRef;
		$[2] = props;
		$[3] = threadViewportStore;
	} else {
		forwardedRef = $[1];
		props = $[2];
		threadViewportStore = $[3];
	}
	const isHoveringRef = useIsHoveringRef();
	const isTopAnchorUser = useIsTopAnchorUser();
	const isTopAnchorTarget = useIsTopAnchorTarget();
	const topAnchorUserRef = useTopAnchorUserRef(isTopAnchorUser, threadViewportStore);
	let t1;
	if ($[4] !== isTopAnchorTarget || $[5] !== threadViewportStore) {
		t1 = {
			active: isTopAnchorTarget,
			threadViewportStore
		};
		$[4] = isTopAnchorTarget;
		$[5] = threadViewportStore;
		$[6] = t1;
	} else t1 = $[6];
	const topAnchorTargetRef = useTopAnchorTargetRef(t1);
	const ref = useComposedRefs(forwardedRef, isHoveringRef, topAnchorUserRef, topAnchorTargetRef);
	const messageId = useAuiState(_temp4);
	const t2 = isTopAnchorUser ? "" : void 0;
	const t3 = isTopAnchorTarget ? "" : void 0;
	let t4;
	if ($[7] !== messageId || $[8] !== props || $[9] !== ref || $[10] !== t2 || $[11] !== t3) {
		t4 = /* @__PURE__ */ jsx(Primitive$1.div, {
			...props,
			ref,
			"data-message-id": messageId,
			"data-aui-top-anchor-user": t2,
			"data-aui-top-anchor-target": t3
		});
		$[7] = messageId;
		$[8] = props;
		$[9] = ref;
		$[10] = t2;
		$[11] = t3;
		$[12] = t4;
	} else t4 = $[12];
	return t4;
};
/**
* The root container component for a message.
*
* This component provides the foundational wrapper for message content and handles
* hover state management for the message. It automatically tracks when the user
* is hovering over the message, which can be used by child components like action bars.
*
* When `turnAnchor="top"` is set on the viewport, this component automatically
* registers itself as the top-anchor user message (when it's the previous user
* message) or as the top-anchor target (when it's the streaming assistant
* response). No additional component is required.
*
* @example
* ```tsx
* <MessagePrimitive.Root>
*   <MessagePrimitive.Content />
*   <ActionBarPrimitive.Root>
*     <ActionBarPrimitive.Copy />
*     <ActionBarPrimitive.Edit />
*   </ActionBarPrimitive.Root>
* </MessagePrimitive.Root>
* ```
*/
const MessagePrimitiveRoot = forwardRef((props, forwardedRef) => {
	const $ = c(7);
	const threadViewportStore = useThreadViewportStore();
	if (threadViewportStore.getState().turnAnchor === "top") {
		let t0;
		if ($[0] !== forwardedRef || $[1] !== props || $[2] !== threadViewportStore) {
			t0 = /* @__PURE__ */ jsx(MessagePrimitiveRootTopAnchor, {
				...props,
				forwardedRef,
				threadViewportStore
			});
			$[0] = forwardedRef;
			$[1] = props;
			$[2] = threadViewportStore;
			$[3] = t0;
		} else t0 = $[3];
		return t0;
	}
	let t0;
	if ($[4] !== forwardedRef || $[5] !== props) {
		t0 = /* @__PURE__ */ jsx(MessagePrimitiveRootDefault, {
			...props,
			forwardedRef
		});
		$[4] = forwardedRef;
		$[5] = props;
		$[6] = t0;
	} else t0 = $[6];
	return t0;
});
MessagePrimitiveRoot.displayName = "MessagePrimitive.Root";
function _temp(s) {
	return s.topAnchorTurn?.anchorId;
}
function _temp2(s) {
	return s.topAnchorTurn?.targetId;
}
function _temp3(s) {
	return s.message.id;
}
function _temp4(s) {
	return s.message.id;
}
//#endregion
export { MessagePrimitiveRoot };
