"use client";
import { Primitive as Primitive$1 } from "../../utils/Primitive.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { forwardRef } from "@assistant-ui/tap/react-shim";
import { useAui, useAuiState } from "@assistant-ui/store";
import { jsx } from "react/jsx-runtime";
import { composeEventHandlers } from "radix-ui/internal";
//#region src/primitives/actionBar/ActionBarExportMarkdown.tsx
const useActionBarExportMarkdown = (t0) => {
	const $ = c(6);
	let t1;
	if ($[0] !== t0) {
		t1 = t0 === void 0 ? {} : t0;
		$[0] = t0;
		$[1] = t1;
	} else t1 = $[1];
	const { filename, onExport } = t1;
	const aui = useAui();
	const hasExportableContent = useAuiState(_temp2);
	let t2;
	if ($[2] !== aui.message || $[3] !== filename || $[4] !== onExport) {
		t2 = async () => {
			const content = aui.message.getCopyText();
			if (!content) return;
			if (onExport) {
				await onExport(content);
				return;
			}
			const blob = new Blob([content], { type: "text/markdown" });
			const url = URL.createObjectURL(blob);
			const a = document.createElement("a");
			a.href = url;
			a.download = filename ?? `message-${Date.now()}.md`;
			a.rel = "noopener";
			document.body.appendChild(a);
			a.click();
			document.body.removeChild(a);
			setTimeout(() => URL.revokeObjectURL(url), 4e4);
		};
		$[2] = aui.message;
		$[3] = filename;
		$[4] = onExport;
		$[5] = t2;
	} else t2 = $[5];
	const callback = t2;
	if (!hasExportableContent) return null;
	return callback;
};
const ActionBarPrimitiveExportMarkdown = forwardRef((t0, forwardedRef) => {
	const $ = c(19);
	let disabled;
	let filename;
	let onClick;
	let onExport;
	let props;
	if ($[0] !== t0) {
		({filename, onExport, onClick, disabled, ...props} = t0);
		$[0] = t0;
		$[1] = disabled;
		$[2] = filename;
		$[3] = onClick;
		$[4] = onExport;
		$[5] = props;
	} else {
		disabled = $[1];
		filename = $[2];
		onClick = $[3];
		onExport = $[4];
		props = $[5];
	}
	let t1;
	if ($[6] !== filename || $[7] !== onExport) {
		t1 = {
			filename,
			onExport
		};
		$[6] = filename;
		$[7] = onExport;
		$[8] = t1;
	} else t1 = $[8];
	const callback = useActionBarExportMarkdown(t1);
	const t2 = disabled || !callback;
	let t3;
	if ($[9] !== callback) {
		t3 = () => {
			callback?.().catch(_temp3);
		};
		$[9] = callback;
		$[10] = t3;
	} else t3 = $[10];
	let t4;
	if ($[11] !== onClick || $[12] !== t3) {
		t4 = composeEventHandlers(onClick, t3);
		$[11] = onClick;
		$[12] = t3;
		$[13] = t4;
	} else t4 = $[13];
	let t5;
	if ($[14] !== forwardedRef || $[15] !== props || $[16] !== t2 || $[17] !== t4) {
		t5 = /* @__PURE__ */ jsx(Primitive$1.button, {
			type: "button",
			...props,
			ref: forwardedRef,
			disabled: t2,
			onClick: t4
		});
		$[14] = forwardedRef;
		$[15] = props;
		$[16] = t2;
		$[17] = t4;
		$[18] = t5;
	} else t5 = $[18];
	return t5;
});
ActionBarPrimitiveExportMarkdown.displayName = "ActionBarPrimitive.ExportMarkdown";
function _temp(c) {
	return c.type === "text" && c.text.length > 0;
}
function _temp2(s) {
	return (s.message.role !== "assistant" || s.message.status?.type !== "running") && s.message.parts.some(_temp);
}
function _temp3(error) {
	console.error("[assistant-ui] markdown export failed:", error);
}
//#endregion
export { ActionBarPrimitiveExportMarkdown };
