"use client";
import { Primitive as Primitive$1 } from "../../utils/Primitive.js";
import { useThreadRootElementRef } from "../thread/ThreadRootElementContext.js";
import { getSelectionMessageId } from "../../utils/getSelectionMessageId.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { createContext, forwardRef, useContext, useEffect, useRef, useState } from "@assistant-ui/tap/react-shim";
import { jsx } from "react/jsx-runtime";
import { composeEventHandlers } from "radix-ui/internal";
import { createPortal } from "react-dom";
//#region src/primitives/selectionToolbar/SelectionToolbarRoot.tsx
const SelectionToolbarContext = createContext(null);
const useSelectionToolbarInfo = () => {
	return useContext(SelectionToolbarContext);
};
/**
* A floating toolbar that appears when text is selected within a message.
*
* Listens for browser selection changes, validates that the selection is
* within a single message, and renders a positioned portal near the
* selection. Prevents mousedown from clearing the selection.
*
* @example
* ```tsx
* <SelectionToolbarPrimitive.Root>
*   <SelectionToolbarPrimitive.Quote>Quote</SelectionToolbarPrimitive.Quote>
* </SelectionToolbarPrimitive.Root>
* ```
*/
const SelectionToolbarPrimitiveRoot = forwardRef((t0, forwardedRef) => {
	const $ = c(21);
	let onMouseDown;
	let props;
	let style;
	if ($[0] !== t0) {
		({onMouseDown, style, ...props} = t0);
		$[0] = t0;
		$[1] = onMouseDown;
		$[2] = props;
		$[3] = style;
	} else {
		onMouseDown = $[1];
		props = $[2];
		style = $[3];
	}
	const [info, setInfo] = useState(null);
	const threadRootRef = useThreadRootElementRef();
	const warnedAboutMissingThreadRootRef = useRef(false);
	let t1;
	let t2;
	if ($[4] !== threadRootRef) {
		t1 = () => {
			let pendingFrame = null;
			let isMouseDragging = false;
			const checkSelection = () => {
				if (pendingFrame !== null) cancelAnimationFrame(pendingFrame);
				pendingFrame = requestAnimationFrame(() => {
					pendingFrame = null;
					const sel = window.getSelection();
					if (!sel || sel.isCollapsed) {
						setInfo(null);
						return;
					}
					const text = sel.toString().trim();
					if (!text) {
						setInfo(null);
						return;
					}
					if (threadRootRef && !threadRootRef.current) {
						if (process.env.NODE_ENV !== "production" && !warnedAboutMissingThreadRootRef.current) {
							warnedAboutMissingThreadRootRef.current = true;
							console.warn("[SelectionToolbarPrimitive.Root] ThreadPrimitive.Root did not provide a DOM element, so the selection cannot be scoped to its thread. Ensure a custom root child forwards its ref.");
						}
					}
					const messageId = getSelectionMessageId(sel, threadRootRef?.current);
					if (!messageId) {
						setInfo(null);
						return;
					}
					const rect = sel.getRangeAt(0).getBoundingClientRect();
					setInfo({
						text,
						messageId,
						rect
					});
				});
			};
			const handleSelectionChange = () => {
				const sel_0 = window.getSelection();
				if (!sel_0 || sel_0.isCollapsed) {
					if (pendingFrame !== null) {
						cancelAnimationFrame(pendingFrame);
						pendingFrame = null;
					}
					setInfo(null);
					return;
				}
				if (!isMouseDragging) checkSelection();
			};
			const handleScroll = () => {
				if (pendingFrame !== null) {
					cancelAnimationFrame(pendingFrame);
					pendingFrame = null;
				}
				setInfo(null);
			};
			const handleMouseDown = () => {
				isMouseDragging = true;
			};
			const handleMouseUp = () => {
				isMouseDragging = false;
				checkSelection();
			};
			const handleMouseCancel = () => {
				isMouseDragging = false;
			};
			document.addEventListener("mousedown", handleMouseDown, true);
			document.addEventListener("mouseup", handleMouseUp, true);
			document.addEventListener("dragend", handleMouseUp, true);
			document.addEventListener("contextmenu", handleMouseCancel, true);
			window.addEventListener("blur", handleMouseCancel);
			document.addEventListener("selectionchange", handleSelectionChange);
			document.addEventListener("scroll", handleScroll, true);
			return () => {
				if (pendingFrame !== null) cancelAnimationFrame(pendingFrame);
				document.removeEventListener("mousedown", handleMouseDown, true);
				document.removeEventListener("mouseup", handleMouseUp, true);
				document.removeEventListener("dragend", handleMouseUp, true);
				document.removeEventListener("contextmenu", handleMouseCancel, true);
				window.removeEventListener("blur", handleMouseCancel);
				document.removeEventListener("selectionchange", handleSelectionChange);
				document.removeEventListener("scroll", handleScroll, true);
			};
		};
		t2 = [threadRootRef];
		$[4] = threadRootRef;
		$[5] = t1;
		$[6] = t2;
	} else {
		t1 = $[5];
		t2 = $[6];
	}
	useEffect(t1, t2);
	if (!info) return null;
	const t3 = `${info.rect.top - 8}px`;
	const t4 = `${info.rect.left + info.rect.width / 2}px`;
	let t5;
	if ($[7] !== style || $[8] !== t3 || $[9] !== t4) {
		t5 = {
			position: "fixed",
			top: t3,
			left: t4,
			transform: "translate(-50%, -100%)",
			zIndex: 50,
			...style
		};
		$[7] = style;
		$[8] = t3;
		$[9] = t4;
		$[10] = t5;
	} else t5 = $[10];
	const positionStyle = t5;
	let t6;
	if ($[11] !== onMouseDown) {
		t6 = composeEventHandlers(onMouseDown, _temp);
		$[11] = onMouseDown;
		$[12] = t6;
	} else t6 = $[12];
	let t7;
	if ($[13] !== forwardedRef || $[14] !== positionStyle || $[15] !== props || $[16] !== t6) {
		t7 = /* @__PURE__ */ jsx(Primitive$1.div, {
			...props,
			ref: forwardedRef,
			style: positionStyle,
			onMouseDown: t6
		});
		$[13] = forwardedRef;
		$[14] = positionStyle;
		$[15] = props;
		$[16] = t6;
		$[17] = t7;
	} else t7 = $[17];
	let t8;
	if ($[18] !== info || $[19] !== t7) {
		t8 = createPortal(/* @__PURE__ */ jsx(SelectionToolbarContext.Provider, {
			value: info,
			children: t7
		}), document.body);
		$[18] = info;
		$[19] = t7;
		$[20] = t8;
	} else t8 = $[20];
	return t8;
});
SelectionToolbarPrimitiveRoot.displayName = "SelectionToolbarPrimitive.Root";
function _temp(e) {
	e.preventDefault();
}
//#endregion
export { SelectionToolbarPrimitiveRoot, useSelectionToolbarInfo };
