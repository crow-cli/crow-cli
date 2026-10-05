"use client";
import { useDropdownMenuScope } from "./scope.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { createContext, useContext } from "@assistant-ui/tap/react-shim";
import { jsx } from "react/jsx-runtime";
import { useControllableState } from "radix-ui/internal";
import { DropdownMenu } from "radix-ui";
//#region src/primitives/threadListItemMore/ThreadListItemMoreRoot.tsx
const ThreadListItemMoreSetOpenContext = createContext(() => {});
const useThreadListItemMoreSetOpen = () => {
	return useContext(ThreadListItemMoreSetOpenContext);
};
const ThreadListItemMoreSharedFocusGroupContext = createContext(false);
const useThreadListItemMoreSharedFocusGroup = () => {
	return useContext(ThreadListItemMoreSharedFocusGroupContext);
};
/**
* Root container for the overflow menu, built on Radix DropdownMenu.
*
* Defaults to a standard, self-contained modal dropdown. Pass
* {@link ThreadListItemMorePrimitiveRoot.Props.sharedFocusGroup} to fold it into
* the thread list's keyboard navigation instead.
*/
const ThreadListItemMorePrimitiveRoot = (t0) => {
	const $ = c(26);
	let __scopeThreadListItemMore;
	let defaultOpen;
	let modalProp;
	let onOpenChange;
	let openProp;
	let rest;
	let t1;
	if ($[0] !== t0) {
		({__scopeThreadListItemMore, open: openProp, defaultOpen, onOpenChange, sharedFocusGroup: t1, modal: modalProp, ...rest} = t0);
		$[0] = t0;
		$[1] = __scopeThreadListItemMore;
		$[2] = defaultOpen;
		$[3] = modalProp;
		$[4] = onOpenChange;
		$[5] = openProp;
		$[6] = rest;
		$[7] = t1;
	} else {
		__scopeThreadListItemMore = $[1];
		defaultOpen = $[2];
		modalProp = $[3];
		onOpenChange = $[4];
		openProp = $[5];
		rest = $[6];
		t1 = $[7];
	}
	const sharedFocusGroup = t1 === void 0 ? false : t1;
	const modal = sharedFocusGroup ? false : modalProp ?? true;
	const scope = useDropdownMenuScope(__scopeThreadListItemMore);
	const t2 = defaultOpen ?? false;
	let t3;
	if ($[8] !== onOpenChange) {
		t3 = onOpenChange ? { onChange: onOpenChange } : {};
		$[8] = onOpenChange;
		$[9] = t3;
	} else t3 = $[9];
	let t4;
	if ($[10] !== openProp || $[11] !== t2 || $[12] !== t3) {
		t4 = {
			prop: openProp,
			defaultProp: t2,
			caller: "ThreadListItemMorePrimitive.Root",
			...t3
		};
		$[10] = openProp;
		$[11] = t2;
		$[12] = t3;
		$[13] = t4;
	} else t4 = $[13];
	const [open, setOpen] = useControllableState(t4);
	let t5;
	if ($[14] !== modal || $[15] !== open || $[16] !== rest || $[17] !== scope || $[18] !== setOpen) {
		t5 = /* @__PURE__ */ jsx(DropdownMenu.Root, {
			...scope,
			...rest,
			modal,
			open,
			onOpenChange: setOpen
		});
		$[14] = modal;
		$[15] = open;
		$[16] = rest;
		$[17] = scope;
		$[18] = setOpen;
		$[19] = t5;
	} else t5 = $[19];
	let t6;
	if ($[20] !== setOpen || $[21] !== t5) {
		t6 = /* @__PURE__ */ jsx(ThreadListItemMoreSetOpenContext.Provider, {
			value: setOpen,
			children: t5
		});
		$[20] = setOpen;
		$[21] = t5;
		$[22] = t6;
	} else t6 = $[22];
	let t7;
	if ($[23] !== sharedFocusGroup || $[24] !== t6) {
		t7 = /* @__PURE__ */ jsx(ThreadListItemMoreSharedFocusGroupContext.Provider, {
			value: sharedFocusGroup,
			children: t6
		});
		$[23] = sharedFocusGroup;
		$[24] = t6;
		$[25] = t7;
	} else t7 = $[25];
	return t7;
};
ThreadListItemMorePrimitiveRoot.displayName = "ThreadListItemMorePrimitive.Root";
//#endregion
export { ThreadListItemMorePrimitiveRoot, useThreadListItemMoreSetOpen, useThreadListItemMoreSharedFocusGroup };
