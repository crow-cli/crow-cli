"use client";
import { Primitive as Primitive$1 } from "../../utils/Primitive.js";
import { isCompositionKey } from "../../utils/isCompositionKey.js";
import { ThreadRootElementContext } from "./ThreadRootElementContext.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { forwardRef, useEffect, useRef } from "@assistant-ui/tap/react-shim";
import { useAui } from "@assistant-ui/store";
import { jsx } from "react/jsx-runtime";
import { useComposedRefs } from "radix-ui/internal";
//#region src/primitives/thread/ThreadRoot.tsx
const escapeEventThreadRoots = /* @__PURE__ */ new WeakMap();
/**
* The root container component for a thread.
*
* This component serves as the foundational wrapper for all thread-related components.
* It provides the basic structure and context needed for thread functionality.
*
* While this component is mounted, an unhandled Escape keydown inside this thread stops its
* active speech, even if the action bar that started it is no longer mounted. Escape outside
* every thread retains the document-level fallback.
*
* @example
* ```tsx
* <ThreadPrimitive.Root>
*   <ThreadPrimitive.Viewport>
*     <ThreadPrimitive.Messages>
*       {() => <MyMessage />}
*     </ThreadPrimitive.Messages>
*   </ThreadPrimitive.Viewport>
* </ThreadPrimitive.Root>
* ```
*/
const ThreadPrimitiveRoot = forwardRef((props, ref) => {
	const $ = c(9);
	const aui = useAui();
	const rootRef = useRef(null);
	const composedRef = useComposedRefs(ref, rootRef);
	let t0;
	if ($[0] !== props) {
		t0 = (event) => {
			if (event.key === "Escape" && rootRef.current) escapeEventThreadRoots.set(event.nativeEvent, rootRef.current);
			props.onKeyDown?.(event);
		};
		$[0] = props;
		$[1] = t0;
	} else t0 = $[1];
	const handleRootKeyDown = t0;
	let t1;
	let t2;
	if ($[2] !== aui) {
		t1 = () => {
			const handleKeyDown = (event_0) => {
				if (event_0.key !== "Escape") return;
				if (isCompositionKey(event_0)) return;
				if (event_0.defaultPrevented || aui.thread.source === null) return;
				const eventThreadRoot = escapeEventThreadRoots.get(event_0) ?? event_0.composedPath().find(_temp);
				if (eventThreadRoot && eventThreadRoot !== rootRef.current) return;
				if (aui.thread.getState().speech == null) return;
				event_0.preventDefault();
				try {
					aui.thread.stopSpeaking();
				} catch (t3) {
					const error = t3;
					if (!(error instanceof Error) || error.message !== "No message is being spoken") throw error;
				}
			};
			document.addEventListener("keydown", handleKeyDown);
			return () => {
				document.removeEventListener("keydown", handleKeyDown);
			};
		};
		t2 = [aui];
		$[2] = aui;
		$[3] = t1;
		$[4] = t2;
	} else {
		t1 = $[3];
		t2 = $[4];
	}
	useEffect(t1, t2);
	let t3;
	if ($[5] !== composedRef || $[6] !== handleRootKeyDown || $[7] !== props) {
		t3 = /* @__PURE__ */ jsx(ThreadRootElementContext.Provider, {
			value: rootRef,
			children: /* @__PURE__ */ jsx(Primitive$1.div, {
				...props,
				"data-aui-thread-root": "",
				ref: composedRef,
				onKeyDown: handleRootKeyDown
			})
		});
		$[5] = composedRef;
		$[6] = handleRootKeyDown;
		$[7] = props;
		$[8] = t3;
	} else t3 = $[8];
	return t3;
});
ThreadPrimitiveRoot.displayName = "ThreadPrimitive.Root";
function _temp(target) {
	return target instanceof Element && target.hasAttribute("data-aui-thread-root");
}
//#endregion
export { ThreadPrimitiveRoot };
