"use client";
import { useActionBarInteractionContext } from "../actionBar/ActionBarInteractionContext.js";
import { useDropdownMenuScope } from "./scope.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useEffect, useRef } from "@assistant-ui/tap/react-shim";
import { jsx } from "react/jsx-runtime";
import { DropdownMenu } from "radix-ui";
//#region src/primitives/actionBarMore/ActionBarMoreRoot.tsx
const ActionBarMorePrimitiveRoot = (t0) => {
	const $ = c(25);
	let __scopeActionBarMore;
	let onOpenChange;
	let open;
	let rest;
	if ($[0] !== t0) {
		({__scopeActionBarMore, open, onOpenChange, ...rest} = t0);
		$[0] = t0;
		$[1] = __scopeActionBarMore;
		$[2] = onOpenChange;
		$[3] = open;
		$[4] = rest;
	} else {
		__scopeActionBarMore = $[1];
		onOpenChange = $[2];
		open = $[3];
		rest = $[4];
	}
	const scope = useDropdownMenuScope(__scopeActionBarMore);
	const actionBarInteraction = useActionBarInteractionContext();
	const releaseInteractionLockRef = useRef(null);
	const isControlled = open !== void 0;
	let t1;
	if ($[5] !== actionBarInteraction) {
		t1 = (nextOpen) => {
			if (nextOpen) {
				if (releaseInteractionLockRef.current) return;
				releaseInteractionLockRef.current = actionBarInteraction?.acquireInteractionLock() ?? null;
				return;
			}
			releaseInteractionLockRef.current?.();
			releaseInteractionLockRef.current = null;
		};
		$[5] = actionBarInteraction;
		$[6] = t1;
	} else t1 = $[6];
	const setInteractionOpen = t1;
	let t2;
	if ($[7] !== isControlled || $[8] !== onOpenChange || $[9] !== setInteractionOpen) {
		t2 = (nextOpen_0) => {
			if (!isControlled) setInteractionOpen(nextOpen_0);
			onOpenChange?.(nextOpen_0);
		};
		$[7] = isControlled;
		$[8] = onOpenChange;
		$[9] = setInteractionOpen;
		$[10] = t2;
	} else t2 = $[10];
	const handleOpenChange = t2;
	let t3;
	let t4;
	if ($[11] !== isControlled || $[12] !== open || $[13] !== setInteractionOpen) {
		t3 = () => {
			if (!isControlled) return;
			setInteractionOpen(Boolean(open));
		};
		t4 = [
			isControlled,
			open,
			setInteractionOpen
		];
		$[11] = isControlled;
		$[12] = open;
		$[13] = setInteractionOpen;
		$[14] = t3;
		$[15] = t4;
	} else {
		t3 = $[14];
		t4 = $[15];
	}
	useEffect(t3, t4);
	let t5;
	let t6;
	if ($[16] === Symbol.for("react.memo_cache_sentinel")) {
		t5 = () => () => {
			releaseInteractionLockRef.current?.();
			releaseInteractionLockRef.current = null;
		};
		t6 = [];
		$[16] = t5;
		$[17] = t6;
	} else {
		t5 = $[16];
		t6 = $[17];
	}
	useEffect(t5, t6);
	let t7;
	if ($[18] !== open) {
		t7 = open !== void 0 ? { open } : null;
		$[18] = open;
		$[19] = t7;
	} else t7 = $[19];
	let t8;
	if ($[20] !== handleOpenChange || $[21] !== rest || $[22] !== scope || $[23] !== t7) {
		t8 = /* @__PURE__ */ jsx(DropdownMenu.Root, {
			...scope,
			...rest,
			...t7,
			onOpenChange: handleOpenChange
		});
		$[20] = handleOpenChange;
		$[21] = rest;
		$[22] = scope;
		$[23] = t7;
		$[24] = t8;
	} else t8 = $[24];
	return t8;
};
ActionBarMorePrimitiveRoot.displayName = "ActionBarMorePrimitive.Root";
//#endregion
export { ActionBarMorePrimitiveRoot };
