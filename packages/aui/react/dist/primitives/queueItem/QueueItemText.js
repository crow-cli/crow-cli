"use client";
import { Primitive } from "../../utils/Primitive.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { forwardRef } from "@assistant-ui/tap/react-shim";
import { useAuiState } from "@assistant-ui/store";
import { jsx } from "react/jsx-runtime";
//#region src/primitives/queueItem/QueueItemText.tsx
/**
* Renders the prompt text of a queue item.
*
* @example
* ```tsx
* <QueueItemPrimitive.Text />
* ```
*/
const QueueItemPrimitiveText = forwardRef((props, ref) => {
	const $ = c(4);
	const text = useAuiState(_temp3);
	const t0 = props.children ?? text;
	let t1;
	if ($[0] !== props || $[1] !== ref || $[2] !== t0) {
		t1 = /* @__PURE__ */ jsx(Primitive.span, {
			...props,
			ref,
			children: t0
		});
		$[0] = props;
		$[1] = ref;
		$[2] = t0;
		$[3] = t1;
	} else t1 = $[3];
	return t1;
});
QueueItemPrimitiveText.displayName = "QueueItemPrimitive.Text";
function _temp(part) {
	return part.type === "text";
}
function _temp2(part_0) {
	return part_0.text;
}
function _temp3(s) {
	return (s.queueItem.parts ?? []).filter(_temp).map(_temp2).join("\n\n");
}
//#endregion
export { QueueItemPrimitiveText };
