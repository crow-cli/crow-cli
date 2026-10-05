"use client";
import { Primitive } from "../../utils/Primitive.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { forwardRef } from "@assistant-ui/tap/react-shim";
import { useAuiState } from "@assistant-ui/store";
import { jsx } from "react/jsx-runtime";
//#region src/primitives/attachment/AttachmentThumb.tsx
const AttachmentPrimitiveThumb = forwardRef((props, ref) => {
	const $ = c(4);
	const label = useAuiState(_temp);
	const t0 = props.children ?? label;
	let t1;
	if ($[0] !== props || $[1] !== ref || $[2] !== t0) {
		t1 = /* @__PURE__ */ jsx(Primitive.div, {
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
AttachmentPrimitiveThumb.displayName = "AttachmentPrimitive.unstable_Thumb";
function _temp(s) {
	const name = s.attachment.name;
	const dot = name.lastIndexOf(".");
	if (dot > 0 && dot < name.length - 1) return `.${name.slice(dot + 1)}`;
	return s.attachment.type;
}
//#endregion
export { AttachmentPrimitiveThumb };
