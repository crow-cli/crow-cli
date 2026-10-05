"use client";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { createContext, forwardRef, useContext, useEffect, useId, useRef } from "@assistant-ui/tap/react-shim";
import { useAui } from "@assistant-ui/store";
import { jsx } from "react/jsx-runtime";
import { tool } from "@assistant-ui/core";
import { useComposedRefs } from "radix-ui/internal";
//#region src/model-context/makeAssistantVisible.tsx
const click = tool({
	parameters: {
		type: "object",
		properties: { clickId: { type: "string" } },
		required: ["clickId"]
	},
	execute: async ({ clickId }) => {
		const escapedClickId = CSS.escape(clickId);
		const el = document.querySelector(`[data-click-id='${escapedClickId}']`);
		if (el instanceof HTMLElement) {
			el.click();
			await new Promise((resolve) => setTimeout(resolve, 2e3));
			return {};
		} else return "Element not found";
	}
});
const setNativeValue = (element, value) => {
	const prototype = element instanceof HTMLInputElement ? HTMLInputElement.prototype : HTMLTextAreaElement.prototype;
	const setter = Object.getOwnPropertyDescriptor(prototype, "value")?.set;
	if (setter) setter.call(element, value);
	else element.value = value;
};
const edit = tool({
	parameters: {
		type: "object",
		properties: {
			editId: { type: "string" },
			value: { type: "string" }
		},
		required: ["editId", "value"]
	},
	execute: async ({ editId, value }) => {
		const escapedEditId = CSS.escape(editId);
		const el = document.querySelector(`[data-edit-id='${escapedEditId}']`);
		if (el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement) {
			setNativeValue(el, value);
			el.dispatchEvent(new Event("input", { bubbles: true }));
			el.dispatchEvent(new Event("change", { bubbles: true }));
			await new Promise((resolve) => setTimeout(resolve, 2e3));
			return {};
		} else return "Element not found";
	}
});
const ReadableContext = createContext(false);
const makeAssistantVisible = (Component, config) => {
	const ReadableComponent = forwardRef((props, outerRef) => {
		const $ = c(15);
		const isNestedReadable = useContext(ReadableContext);
		const clickId = useId();
		const componentRef = useRef(null);
		const aui = useAui();
		let t0;
		if ($[0] === Symbol.for("react.memo_cache_sentinel")) {
			t0 = config ?? {};
			$[0] = t0;
		} else t0 = $[0];
		const { clickable, editable } = t0;
		let t1;
		if ($[1] !== aui.modelContext || $[2] !== isNestedReadable) {
			t1 = () => aui.modelContext.register({ getModelContext: () => ({
				tools: {
					...clickable ? { click } : {},
					...editable ? { edit } : {}
				},
				system: !isNestedReadable ? componentRef.current?.outerHTML : void 0
			}) });
			$[1] = aui.modelContext;
			$[2] = isNestedReadable;
			$[3] = t1;
		} else t1 = $[3];
		let t2;
		if ($[4] !== aui || $[5] !== isNestedReadable) {
			t2 = [
				isNestedReadable,
				aui,
				clickable,
				editable
			];
			$[4] = aui;
			$[5] = isNestedReadable;
			$[6] = t2;
		} else t2 = $[6];
		useEffect(t1, t2);
		const ref = useComposedRefs(componentRef, outerRef);
		const t3 = props;
		let t4;
		let t5;
		if ($[7] !== clickId) {
			t4 = config?.clickable ? { "data-click-id": clickId } : {};
			t5 = config?.editable ? { "data-edit-id": clickId } : {};
			$[7] = clickId;
			$[8] = t4;
			$[9] = t5;
		} else {
			t4 = $[8];
			t5 = $[9];
		}
		let t6;
		if ($[10] !== ref || $[11] !== t3 || $[12] !== t4 || $[13] !== t5) {
			t6 = /* @__PURE__ */ jsx(ReadableContext.Provider, {
				value: true,
				children: /* @__PURE__ */ jsx(Component, {
					...t3,
					...t4,
					...t5,
					ref
				})
			});
			$[10] = ref;
			$[11] = t3;
			$[12] = t4;
			$[13] = t5;
			$[14] = t6;
		} else t6 = $[14];
		return t6;
	});
	ReadableComponent.displayName = Component.displayName;
	return ReadableComponent;
};
//#endregion
export { makeAssistantVisible as default, makeAssistantVisible };
