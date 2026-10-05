"use client";
import { usePopoverScope } from "./scope.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useState } from "@assistant-ui/tap/react-shim";
import { useAuiEvent } from "@assistant-ui/store";
import { jsx } from "react/jsx-runtime";
import { Popover } from "radix-ui";
//#region src/primitives/assistantModal/AssistantModalRoot.tsx
const AssistantModalPrimitiveRoot = (t0) => {
	const $ = c(18);
	let __scopeAssistantModal;
	let onOpenChange;
	let open;
	let rest;
	let t1;
	let t2;
	if ($[0] !== t0) {
		({__scopeAssistantModal, defaultOpen: t1, unstable_openOnRunStart: t2, open, onOpenChange, ...rest} = t0);
		$[0] = t0;
		$[1] = __scopeAssistantModal;
		$[2] = onOpenChange;
		$[3] = open;
		$[4] = rest;
		$[5] = t1;
		$[6] = t2;
	} else {
		__scopeAssistantModal = $[1];
		onOpenChange = $[2];
		open = $[3];
		rest = $[4];
		t1 = $[5];
		t2 = $[6];
	}
	const defaultOpen = t1 === void 0 ? false : t1;
	const unstable_openOnRunStart = t2 === void 0 ? true : t2;
	const scope = usePopoverScope(__scopeAssistantModal);
	const [modalOpen, setOpen] = useState(defaultOpen);
	const isOpen = open ?? modalOpen;
	let t3;
	if ($[7] !== onOpenChange) {
		t3 = (open_0) => {
			onOpenChange?.(open_0);
			setOpen(open_0);
		};
		$[7] = onOpenChange;
		$[8] = t3;
	} else t3 = $[8];
	const openChangeHandler = t3;
	let t4;
	if ($[9] !== isOpen || $[10] !== openChangeHandler || $[11] !== unstable_openOnRunStart) {
		t4 = () => {
			if (unstable_openOnRunStart && !isOpen) openChangeHandler(true);
		};
		$[9] = isOpen;
		$[10] = openChangeHandler;
		$[11] = unstable_openOnRunStart;
		$[12] = t4;
	} else t4 = $[12];
	useAuiEvent("thread.runStart", t4);
	let t5;
	if ($[13] !== isOpen || $[14] !== openChangeHandler || $[15] !== rest || $[16] !== scope) {
		t5 = /* @__PURE__ */ jsx(Popover.Root, {
			...scope,
			open: isOpen,
			onOpenChange: openChangeHandler,
			...rest
		});
		$[13] = isOpen;
		$[14] = openChangeHandler;
		$[15] = rest;
		$[16] = scope;
		$[17] = t5;
	} else t5 = $[17];
	return t5;
};
AssistantModalPrimitiveRoot.displayName = "AssistantModalPrimitive.Root";
//#endregion
export { AssistantModalPrimitiveRoot };
