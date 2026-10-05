import { Primitive as Primitive$1 } from "./Primitive.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { forwardRef } from "@assistant-ui/tap/react-shim";
import { jsx } from "react/jsx-runtime";
import { composeEventHandlers } from "radix-ui/internal";
//#region src/utils/createActionButton.tsx
const createActionButton = (displayName, useActionButton, forwardProps = []) => {
	const ActionButton = forwardRef((props, forwardedRef) => {
		const $ = c(6);
		const forwardedProps = {};
		const primitiveProps = {};
		Object.keys(props).forEach((key) => {
			if (forwardProps.includes(key)) forwardedProps[key] = props[key];
			else primitiveProps[key] = props[key];
		});
		const callback = useActionButton(forwardedProps) ?? void 0;
		const t0 = Primitive$1;
		const t1 = "button";
		const t2 = primitiveProps.disabled || !callback;
		const t3 = composeEventHandlers(primitiveProps.onClick, callback);
		let t4;
		if ($[0] !== forwardedRef || $[1] !== primitiveProps || $[2] !== t0.button || $[3] !== t2 || $[4] !== t3) {
			t4 = /* @__PURE__ */ jsx(t0.button, {
				type: t1,
				...primitiveProps,
				ref: forwardedRef,
				disabled: t2,
				onClick: t3
			});
			$[0] = forwardedRef;
			$[1] = primitiveProps;
			$[2] = t0.button;
			$[3] = t2;
			$[4] = t3;
			$[5] = t4;
		} else t4 = $[5];
		return t4;
	});
	ActionButton.displayName = displayName;
	return ActionButton;
};
//#endregion
export { createActionButton };
