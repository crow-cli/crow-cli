"use client";
import { Primitive } from "../../utils/Primitive.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useMessageError } from "@assistant-ui/core/react";
import { forwardRef } from "@assistant-ui/tap/react-shim";
import { jsx } from "react/jsx-runtime";
//#region src/primitives/error/ErrorMessage.tsx
const ErrorPrimitiveMessage = forwardRef((t0, forwardRef) => {
	const $ = c(7);
	let children;
	let props;
	if ($[0] !== t0) {
		({children, ...props} = t0);
		$[0] = t0;
		$[1] = children;
		$[2] = props;
	} else {
		children = $[1];
		props = $[2];
	}
	const error = useMessageError();
	if (error === void 0) return null;
	const t1 = children ?? String(error);
	let t2;
	if ($[3] !== forwardRef || $[4] !== props || $[5] !== t1) {
		t2 = /* @__PURE__ */ jsx(Primitive.span, {
			...props,
			ref: forwardRef,
			children: t1
		});
		$[3] = forwardRef;
		$[4] = props;
		$[5] = t1;
		$[6] = t2;
	} else t2 = $[6];
	return t2;
});
ErrorPrimitiveMessage.displayName = "ErrorPrimitive.Message";
//#endregion
export { ErrorPrimitiveMessage };
