"use client";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { createElement } from "@assistant-ui/tap/react-shim";
import { useAuiState } from "@assistant-ui/store";
import { Fragment as Fragment$1, jsx } from "react/jsx-runtime";
//#region src/react/primitives/generativeUI/GenerativeUI.tsx
/**
* Thrown when a generative-ui spec references a component name that is not
* present in the consumer-provided allowlist. The allowlist is the security
* boundary in the same-realm rendering path — there is no fallback by
* default. Pass `Fallback` to opt into a soft-fail UX.
*/
var GenerativeUIRenderError = class extends Error {
	componentName;
	constructor(componentName, message = `Component "${componentName}" is not in the generative-ui allowlist.`) {
		super(message);
		this.name = "GenerativeUIRenderError";
		this.componentName = componentName;
	}
};
const isObjectNode = (node) => typeof node === "object" && node !== null && !Array.isArray(node);
const toNodeList = (value) => {
	if (value === void 0 || value === null) return [];
	return Array.isArray(value) ? value : [value];
};
const warn = (message, ...args) => {
	if (typeof process !== "undefined" && process.env?.NODE_ENV !== "production") console.warn(message, ...args);
};
/** Bounds recursion so a runaway or adversarial model response cannot overflow the stack. */
const MAX_DEPTH = 64;
const renderNode = (node, components, Fallback, path, depth = 0) => {
	if (depth > MAX_DEPTH) {
		warn(`[generative-ui] Skipping node nested past ${MAX_DEPTH} levels at ${path}.`);
		return null;
	}
	if (node === void 0 || node === null) return null;
	if (typeof node === "string" || typeof node === "number") return node;
	if (Array.isArray(node)) return node.map((child, i) => renderNode(child, components, Fallback, `${path}/${i}`, depth + 1));
	if (!isObjectNode(node) || !("component" in node) || typeof node.component !== "string") {
		warn(`[generative-ui] Skipping malformed node at ${path}:`, node);
		return null;
	}
	const { component, props, children, key } = node;
	const Resolved = Object.hasOwn(components, component) ? components[component] : void 0;
	if (!Resolved) {
		if (Fallback) return /* @__PURE__ */ jsx(Fallback, {
			component,
			props
		}, key ?? path);
		throw new GenerativeUIRenderError(component);
	}
	return createElement(Resolved, {
		...props ?? {},
		key: key ?? path
	}, ...toNodeList(children).map((child, i) => renderNode(child, components, Fallback, `${path}/${i}`, depth + 1)));
};
/**
* Internal renderer. Resolves a {@link GenerativeUISpec} against the consumer
* allowlist. Used by `MessagePrimitive.GenerativeUI` and by
* `MessagePrimitive.Parts` when handling a `generative-ui` part.
*/
const GenerativeUIRender = (t0) => {
	const $ = c(11);
	const { spec, components, Fallback } = t0;
	const t1 = spec?.root;
	let t2;
	if ($[0] !== t1) {
		t2 = toNodeList(t1);
		$[0] = t1;
		$[1] = t2;
	} else t2 = $[1];
	const nodes = t2;
	let t3;
	if ($[2] !== Fallback || $[3] !== components || $[4] !== nodes) {
		let t4;
		if ($[6] !== Fallback || $[7] !== components) {
			t4 = (node, i) => renderNode(node, components, Fallback, `${i}`);
			$[6] = Fallback;
			$[7] = components;
			$[8] = t4;
		} else t4 = $[8];
		t3 = nodes.map(t4);
		$[2] = Fallback;
		$[3] = components;
		$[4] = nodes;
		$[5] = t3;
	} else t3 = $[5];
	let t4;
	if ($[9] !== t3) {
		t4 = /* @__PURE__ */ jsx(Fragment$1, { children: t3 });
		$[9] = t3;
		$[10] = t4;
	} else t4 = $[10];
	return t4;
};
GenerativeUIRender.displayName = "GenerativeUIRender";
/**
* Renders a generative-ui message part using a consumer-provided allowlist.
*
* The agent emits a `generative-ui` message part containing a JSON spec
* (see {@link GenerativeUISpec}). This primitive walks the spec and resolves
* each `component` name against the allowlist. Names not in the allowlist
* throw {@link GenerativeUIRenderError} unless a `Fallback` is provided.
*
* Stream-friendly: a partial spec renders progressively as it is filled in.
*
* @example
* ```tsx
* <MessagePrimitive.GenerativeUI
*   components={{ Card: MyCard, Button: MyButton }}
* />
* ```
*/
const MessagePrimitiveGenerativeUI = (t0) => {
	const $ = c(4);
	const { components, spec, Fallback } = t0;
	const storeSpec = useAuiState(_temp);
	const partSpec = spec ?? storeSpec;
	if (!partSpec) return null;
	let t1;
	if ($[0] !== Fallback || $[1] !== components || $[2] !== partSpec) {
		t1 = /* @__PURE__ */ jsx(GenerativeUIRender, {
			spec: partSpec,
			components,
			Fallback
		});
		$[0] = Fallback;
		$[1] = components;
		$[2] = partSpec;
		$[3] = t1;
	} else t1 = $[3];
	return t1;
};
MessagePrimitiveGenerativeUI.displayName = "MessagePrimitive.GenerativeUI";
function _temp(s) {
	const part = s.part;
	return part?.type === "generative-ui" ? part.spec : void 0;
}
//#endregion
export { GenerativeUIRender, GenerativeUIRenderError, MessagePrimitiveGenerativeUI };
