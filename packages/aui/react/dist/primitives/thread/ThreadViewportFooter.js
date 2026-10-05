"use client";
import { useThreadViewport } from "../../context/react/ThreadViewportContext.js";
import { Primitive as Primitive$1 } from "../../utils/Primitive.js";
import { useSizeHandle } from "../../utils/hooks/useSizeHandle.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { forwardRef } from "@assistant-ui/tap/react-shim";
import { jsx } from "react/jsx-runtime";
import { useComposedRefs } from "radix-ui/internal";
//#region src/primitives/thread/ThreadViewportFooter.tsx
/**
* A footer container that measures its height for scroll calculations.
*
* This component measures its height and provides it to the viewport context
* so the auto-scroll system can account for any sticky footer overlapping the
* message list.
*
* Multiple ViewportFooter components can be used - their heights are summed.
*
* Typically used with `className="sticky bottom-0"` to keep the footer
* visible at the bottom of the viewport while scrolling.
*
* @example
* ```tsx
* <ThreadPrimitive.Viewport>
*   <ThreadPrimitive.Messages>
*     {() => <MyMessage />}
*   </ThreadPrimitive.Messages>
*   <ThreadPrimitive.ViewportFooter className="sticky bottom-0">
*     <Composer />
*   </ThreadPrimitive.ViewportFooter>
* </ThreadPrimitive.Viewport>
* ```
*/
const ThreadPrimitiveViewportFooter = forwardRef((props, forwardedRef) => {
	const $ = c(3);
	const register = useThreadViewport(_temp);
	const resizeRef = useSizeHandle(register, _temp2);
	const ref = useComposedRefs(forwardedRef, resizeRef);
	let t0;
	if ($[0] !== props || $[1] !== ref) {
		t0 = /* @__PURE__ */ jsx(Primitive$1.div, {
			...props,
			ref
		});
		$[0] = props;
		$[1] = ref;
		$[2] = t0;
	} else t0 = $[2];
	return t0;
});
ThreadPrimitiveViewportFooter.displayName = "ThreadPrimitive.ViewportFooter";
function _temp(s) {
	return s.registerContentInset;
}
function _temp2(el) {
	const marginTop = parseFloat(getComputedStyle(el).marginTop) || 0;
	return el.offsetHeight + marginTop;
}
//#endregion
export { ThreadPrimitiveViewportFooter };
