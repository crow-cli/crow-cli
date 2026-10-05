"use client";
import { MessagePartPrimitiveText } from "../messagePart/MessagePartText.js";
import { MessagePartPrimitiveImage } from "../messagePart/MessagePartImage.js";
import { MessagePartPrimitiveInProgress } from "../messagePart/MessagePartInProgress.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { MessagePartComponent as MessagePartComponentBase, MessagePrimitivePartByIndex as MessagePrimitivePartByIndexBase, MessagePrimitiveParts as MessagePrimitiveParts$1, messagePartsDefaultComponents } from "@assistant-ui/core/react";
import { jsx, jsxs } from "react/jsx-runtime";
//#region src/primitives/message/MessageParts.tsx
const webDefaultComponents = {
	...messagePartsDefaultComponents,
	Text: () => /* @__PURE__ */ jsxs("p", {
		style: { whiteSpace: "pre-line" },
		children: [/* @__PURE__ */ jsx(MessagePartPrimitiveText, {}), /* @__PURE__ */ jsx(MessagePartPrimitiveInProgress, { children: /* @__PURE__ */ jsx("span", {
			style: { fontFamily: "revert" },
			children: " ●"
		}) })]
	}),
	Image: () => /* @__PURE__ */ jsx(MessagePartPrimitiveImage, {})
};
/**
* Renders the parts of a message with web-specific default components.
*/
const MessagePrimitiveParts = (props) => {
	const $ = c(10);
	if ("children" in props) {
		let t0;
		if ($[0] !== props.children) {
			t0 = /* @__PURE__ */ jsx(MessagePrimitiveParts$1, { children: props.children });
			$[0] = props.children;
			$[1] = t0;
		} else t0 = $[1];
		return t0;
	}
	let components;
	let rest;
	if ($[2] !== props) {
		({components, ...rest} = props);
		$[2] = props;
		$[3] = components;
		$[4] = rest;
	} else {
		components = $[3];
		rest = $[4];
	}
	let t0;
	if ($[5] !== components) {
		t0 = components ? {
			...components,
			Text: components.Text ?? webDefaultComponents.Text,
			Image: components.Image ?? webDefaultComponents.Image
		} : webDefaultComponents;
		$[5] = components;
		$[6] = t0;
	} else t0 = $[6];
	const t1 = t0;
	let t2;
	if ($[7] !== rest || $[8] !== t1) {
		t2 = /* @__PURE__ */ jsx(MessagePrimitiveParts$1, {
			components: t1,
			...rest
		});
		$[7] = rest;
		$[8] = t1;
		$[9] = t2;
	} else t2 = $[9];
	return t2;
};
MessagePrimitiveParts.displayName = "MessagePrimitive.Parts";
//#endregion
export { MessagePartComponentBase as MessagePartComponent, MessagePrimitivePartByIndexBase as MessagePrimitivePartByIndex, MessagePrimitiveParts };
