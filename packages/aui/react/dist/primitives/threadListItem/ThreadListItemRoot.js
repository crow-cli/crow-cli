"use client";
import { Primitive as Primitive$1 } from "../../utils/Primitive.js";
import { ThreadListItemFocusProvider, useThreadListCollection } from "../threadListFocusGroup.js";
import { forwardRef, useMemo, useRef } from "@assistant-ui/tap/react-shim";
import { useAuiState } from "@assistant-ui/store";
import { jsx } from "react/jsx-runtime";
import { composeEventHandlers } from "radix-ui/internal";
import { Direction } from "radix-ui";
//#region src/primitives/threadListItem/ThreadListItemRoot.tsx
const ThreadListItemPrimitiveRoot = forwardRef((props, ref) => {
	const isMain = useAuiState((s) => s.threads.mainThreadId === s.threadListItem.id);
	const triggerRef = useRef(null);
	const moreRef = useRef(null);
	const focus = useMemo(() => ({
		triggerRef,
		moreRef
	}), []);
	const getItems = useThreadListCollection(void 0);
	const direction = Direction.useDirection();
	const onKeyDown = (event) => {
		if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
		const forwardKey = direction === "rtl" ? "ArrowLeft" : "ArrowRight";
		const backKey = direction === "rtl" ? "ArrowRight" : "ArrowLeft";
		const trigger = triggerRef.current;
		const more = moreRef.current;
		if (trigger && event.target === trigger) {
			if (event.key === "ArrowDown" || event.key === "ArrowUp") {
				const triggers = getItems().map((item) => item.ref.current).filter((node) => node !== null);
				const next = triggers[triggers.indexOf(trigger) + (event.key === "ArrowDown" ? 1 : -1)];
				if (next) {
					next.focus();
					event.preventDefault();
				}
			} else if (event.key === forwardKey && more) {
				more.focus();
				event.preventDefault();
			}
		} else if (more && event.target === more && event.key === backKey) {
			trigger?.focus();
			event.preventDefault();
		}
	};
	return /* @__PURE__ */ jsx(ThreadListItemFocusProvider, {
		value: focus,
		children: /* @__PURE__ */ jsx(Primitive$1.div, {
			...isMain ? {
				"data-active": "true",
				"aria-current": "true"
			} : null,
			...props,
			onKeyDown: composeEventHandlers(props.onKeyDown, onKeyDown),
			ref
		})
	});
});
ThreadListItemPrimitiveRoot.displayName = "ThreadListItemPrimitive.Root";
//#endregion
export { ThreadListItemPrimitiveRoot };
