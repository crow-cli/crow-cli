"use client";
import { Primitive } from "../../utils/Primitive.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { forwardRef } from "@assistant-ui/tap/react-shim";
import { jsx } from "react/jsx-runtime";
//#region src/primitives/error/ErrorRoot.tsx
const ErrorPrimitiveRoot = forwardRef((props, forwardRef) => {
	const $ = c(3);
	let t0;
	if ($[0] !== forwardRef || $[1] !== props) {
		t0 = /* @__PURE__ */ jsx(Primitive.div, {
			role: "alert",
			...props,
			ref: forwardRef
		});
		$[0] = forwardRef;
		$[1] = props;
		$[2] = t0;
	} else t0 = $[2];
	return t0;
});
ErrorPrimitiveRoot.displayName = "ErrorPrimitive.Root";
//#endregion
export { ErrorPrimitiveRoot };
