"use client";
import { Primitive } from "../../utils/Primitive.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { forwardRef } from "@assistant-ui/tap/react-shim";
import { jsx } from "react/jsx-runtime";
//#region src/primitives/attachment/AttachmentRoot.tsx
/**
* The root container component for an attachment.
*
* This component provides the foundational wrapper for attachment-related components
* and content. It serves as the context provider for attachment state and actions.
*
* @example
* ```tsx
* <AttachmentPrimitive.Root>
*   <AttachmentPrimitive.Name />
*   <AttachmentPrimitive.Remove />
* </AttachmentPrimitive.Root>
* ```
*/
const AttachmentPrimitiveRoot = forwardRef((props, ref) => {
	const $ = c(3);
	let t0;
	if ($[0] !== props || $[1] !== ref) {
		t0 = /* @__PURE__ */ jsx(Primitive.div, {
			...props,
			ref
		});
		$[0] = props;
		$[1] = ref;
		$[2] = t0;
	} else t0 = $[2];
	return t0;
});
AttachmentPrimitiveRoot.displayName = "AttachmentPrimitive.Root";
//#endregion
export { AttachmentPrimitiveRoot };
