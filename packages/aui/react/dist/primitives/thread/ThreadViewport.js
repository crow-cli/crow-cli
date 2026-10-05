"use client";
import { useThreadViewport, useThreadViewportStore } from "../../context/react/ThreadViewportContext.js";
import { ThreadPrimitiveViewportProvider } from "../../context/providers/ThreadViewportProvider.js";
import { Primitive as Primitive$1 } from "../../utils/Primitive.js";
import { useManagedRef } from "../../utils/hooks/useManagedRef.js";
import { useThreadViewportAutoScroll } from "./useThreadViewportAutoScroll.js";
import { useSizeHandle } from "../../utils/hooks/useSizeHandle.js";
import { useTopAnchorReserve } from "./topAnchor/useTopAnchorReserve.js";
import { getActiveTopAnchorAnchorId, getActiveTopAnchorTargetId, isTopAnchorTurnValid } from "./topAnchor/topAnchorTurn.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { forwardRef, useLayoutEffect } from "@assistant-ui/tap/react-shim";
import { useAuiState } from "@assistant-ui/store";
import { jsx } from "react/jsx-runtime";
import { useComposedRefs } from "radix-ui/internal";
//#region src/primitives/thread/ThreadViewport.tsx
const useViewportSizeRef = () => {
	const register = useThreadViewport(_temp);
	return useSizeHandle(register, _temp2);
};
const useViewportElementRef = () => {
	const registerViewportElement = useThreadViewport(_temp3);
	return useManagedRef(registerViewportElement);
};
const useTopAnchorTurn = (enabled) => {
	const $ = c(19);
	const threadViewportStore = useThreadViewportStore();
	let t0;
	if ($[0] !== enabled) {
		t0 = (s) => {
			if (!enabled) return;
			return getActiveTopAnchorAnchorId(s.thread);
		};
		$[0] = enabled;
		$[1] = t0;
	} else t0 = $[1];
	const activeAnchorId = useAuiState(t0);
	let t1;
	if ($[2] !== enabled) {
		t1 = (s_0) => {
			if (!enabled) return;
			return getActiveTopAnchorTargetId(s_0.thread);
		};
		$[2] = enabled;
		$[3] = t1;
	} else t1 = $[3];
	const activeTargetId = useAuiState(t1);
	const topAnchorTurn = useThreadViewport(_temp4);
	let t2;
	bb0: {
		if (!activeAnchorId || !activeTargetId) {
			t2 = null;
			break bb0;
		}
		let t3;
		if ($[4] !== activeAnchorId || $[5] !== activeTargetId) {
			t3 = {
				anchorId: activeAnchorId,
				targetId: activeTargetId
			};
			$[4] = activeAnchorId;
			$[5] = activeTargetId;
			$[6] = t3;
		} else t3 = $[6];
		t2 = t3;
	}
	const activeTurn = t2;
	let t3;
	if ($[7] !== enabled || $[8] !== topAnchorTurn) {
		t3 = (s_2) => enabled && !!topAnchorTurn && isTopAnchorTurnValid(topAnchorTurn, s_2.thread.messages);
		$[7] = enabled;
		$[8] = topAnchorTurn;
		$[9] = t3;
	} else t3 = $[9];
	const topAnchorTurnIsValid = useAuiState(t3);
	let t4;
	let t5;
	if ($[10] !== threadViewportStore || $[11] !== topAnchorTurn || $[12] !== topAnchorTurnIsValid) {
		t4 = () => {
			if (!topAnchorTurn || topAnchorTurnIsValid) return;
			threadViewportStore.getState().setTopAnchorTurn(null);
		};
		t5 = [
			threadViewportStore,
			topAnchorTurn,
			topAnchorTurnIsValid
		];
		$[10] = threadViewportStore;
		$[11] = topAnchorTurn;
		$[12] = topAnchorTurnIsValid;
		$[13] = t4;
		$[14] = t5;
	} else {
		t4 = $[13];
		t5 = $[14];
	}
	useLayoutEffect(t4, t5);
	let t6;
	let t7;
	if ($[15] !== activeTurn || $[16] !== threadViewportStore) {
		t6 = () => {
			if (!activeTurn) return;
			const state = threadViewportStore.getState();
			const current = state.topAnchorTurn;
			if (current?.anchorId === activeTurn.anchorId && current.targetId === activeTurn.targetId) return;
			state.setTopAnchorTurn(activeTurn);
		};
		t7 = [activeTurn, threadViewportStore];
		$[15] = activeTurn;
		$[16] = threadViewportStore;
		$[17] = t6;
		$[18] = t7;
	} else {
		t6 = $[17];
		t7 = $[18];
	}
	useLayoutEffect(t6, t7);
};
const ThreadPrimitiveViewportScrollable = forwardRef((t0, forwardedRef) => {
	const $ = c(18);
	let autoScroll;
	let children;
	let rest;
	let scrollToBottomOnInitialize;
	let scrollToBottomOnRunStart;
	let scrollToBottomOnThreadSwitch;
	if ($[0] !== t0) {
		({autoScroll, scrollToBottomOnRunStart, scrollToBottomOnInitialize, scrollToBottomOnThreadSwitch, children, ...rest} = t0);
		$[0] = t0;
		$[1] = autoScroll;
		$[2] = children;
		$[3] = rest;
		$[4] = scrollToBottomOnInitialize;
		$[5] = scrollToBottomOnRunStart;
		$[6] = scrollToBottomOnThreadSwitch;
	} else {
		autoScroll = $[1];
		children = $[2];
		rest = $[3];
		scrollToBottomOnInitialize = $[4];
		scrollToBottomOnRunStart = $[5];
		scrollToBottomOnThreadSwitch = $[6];
	}
	let t1;
	if ($[7] !== autoScroll || $[8] !== scrollToBottomOnInitialize || $[9] !== scrollToBottomOnRunStart || $[10] !== scrollToBottomOnThreadSwitch) {
		t1 = {
			autoScroll,
			scrollToBottomOnRunStart,
			scrollToBottomOnInitialize,
			scrollToBottomOnThreadSwitch
		};
		$[7] = autoScroll;
		$[8] = scrollToBottomOnInitialize;
		$[9] = scrollToBottomOnRunStart;
		$[10] = scrollToBottomOnThreadSwitch;
		$[11] = t1;
	} else t1 = $[11];
	const autoScrollRef = useThreadViewportAutoScroll(t1);
	const viewportSizeRef = useViewportSizeRef();
	const viewportElementRef = useViewportElementRef();
	const threadViewportStore = useThreadViewportStore();
	let t2;
	if ($[12] !== threadViewportStore) {
		t2 = threadViewportStore.getState();
		$[12] = threadViewportStore;
		$[13] = t2;
	} else t2 = $[13];
	const topAnchorEnabled = t2.turnAnchor === "top";
	useTopAnchorTurn(topAnchorEnabled);
	useTopAnchorReserve(topAnchorEnabled);
	const ref = useComposedRefs(forwardedRef, autoScrollRef, viewportSizeRef, viewportElementRef);
	let t3;
	if ($[14] !== children || $[15] !== ref || $[16] !== rest) {
		t3 = /* @__PURE__ */ jsx(Primitive$1.div, {
			...rest,
			ref,
			children
		});
		$[14] = children;
		$[15] = ref;
		$[16] = rest;
		$[17] = t3;
	} else t3 = $[17];
	return t3;
});
ThreadPrimitiveViewportScrollable.displayName = "ThreadPrimitive.ViewportScrollable";
/**
* A scrollable viewport container for thread messages.
*
* This component provides a scrollable area for displaying thread messages with
* automatic scrolling capabilities. It manages the viewport state and provides
* context for child components to access viewport-related functionality.
*
* @example
* ```tsx
* <ThreadPrimitive.Viewport turnAnchor="top">
*   <ThreadPrimitive.Messages>
*     {() => <MyMessage />}
*   </ThreadPrimitive.Messages>
* </ThreadPrimitive.Viewport>
* ```
*/
const ThreadPrimitiveViewport = forwardRef((t0, ref) => {
	const $ = c(13);
	let props;
	let topAnchorMessageClamp;
	let turnAnchor;
	if ($[0] !== t0) {
		({turnAnchor, topAnchorMessageClamp, ...props} = t0);
		$[0] = t0;
		$[1] = props;
		$[2] = topAnchorMessageClamp;
		$[3] = turnAnchor;
	} else {
		props = $[1];
		topAnchorMessageClamp = $[2];
		turnAnchor = $[3];
	}
	let t1;
	if ($[4] !== topAnchorMessageClamp || $[5] !== turnAnchor) {
		t1 = {
			turnAnchor,
			topAnchorMessageClamp
		};
		$[4] = topAnchorMessageClamp;
		$[5] = turnAnchor;
		$[6] = t1;
	} else t1 = $[6];
	let t2;
	if ($[7] !== props || $[8] !== ref) {
		t2 = /* @__PURE__ */ jsx(ThreadPrimitiveViewportScrollable, {
			...props,
			ref
		});
		$[7] = props;
		$[8] = ref;
		$[9] = t2;
	} else t2 = $[9];
	let t3;
	if ($[10] !== t1 || $[11] !== t2) {
		t3 = /* @__PURE__ */ jsx(ThreadPrimitiveViewportProvider, {
			options: t1,
			children: t2
		});
		$[10] = t1;
		$[11] = t2;
		$[12] = t3;
	} else t3 = $[12];
	return t3;
});
ThreadPrimitiveViewport.displayName = "ThreadPrimitive.Viewport";
function _temp(s) {
	return s.registerViewport;
}
function _temp2(el) {
	return el.clientHeight;
}
function _temp3(s) {
	return s.registerViewportElement;
}
function _temp4(s_1) {
	return s_1.topAnchorTurn;
}
//#endregion
export { ThreadPrimitiveViewport };
