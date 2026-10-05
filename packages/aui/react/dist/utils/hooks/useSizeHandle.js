"use client";
import { useManagedRef } from "./useManagedRef.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import "@assistant-ui/tap/react-shim";
//#region src/utils/hooks/useSizeHandle.ts
/**
* Hook that creates a ref for tracking element size via a SizeHandle.
* Automatically sets up ResizeObserver and reports height changes.
*
* @param register - Function that returns a SizeHandle (e.g., registerContentInset)
* @param getHeight - Optional function to compute height (defaults to el.offsetHeight)
* @returns A ref callback to attach to the element
*/
const useSizeHandle = (register, getHeight) => {
	const $ = c(3);
	let t0;
	if ($[0] !== getHeight || $[1] !== register) {
		t0 = (el) => {
			if (!register) return;
			const sizeHandle = register();
			const updateHeight = () => {
				const height = getHeight ? getHeight(el) : el.offsetHeight;
				sizeHandle.setHeight(height);
			};
			const ro = new ResizeObserver(updateHeight);
			ro.observe(el);
			updateHeight();
			return () => {
				ro.disconnect();
				sizeHandle.unregister();
			};
		};
		$[0] = getHeight;
		$[1] = register;
		$[2] = t0;
	} else t0 = $[2];
	return useManagedRef(t0);
};
//#endregion
export { useSizeHandle };
