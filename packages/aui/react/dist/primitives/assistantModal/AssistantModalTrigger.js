import { usePopoverScope } from "./scope.js";
import { PopoverRenderTrigger } from "./popoverRenderPrimitives.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { forwardRef } from "@assistant-ui/tap/react-shim";
import { jsx } from "react/jsx-runtime";
//#region src/primitives/assistantModal/AssistantModalTrigger.tsx
const AssistantModalPrimitiveTrigger = forwardRef((t0, ref) => {
	const $ = c(7);
	let __scopeAssistantModal;
	let rest;
	if ($[0] !== t0) {
		({__scopeAssistantModal, ...rest} = t0);
		$[0] = t0;
		$[1] = __scopeAssistantModal;
		$[2] = rest;
	} else {
		__scopeAssistantModal = $[1];
		rest = $[2];
	}
	const scope = usePopoverScope(__scopeAssistantModal);
	let t1;
	if ($[3] !== ref || $[4] !== rest || $[5] !== scope) {
		t1 = /* @__PURE__ */ jsx(PopoverRenderTrigger, {
			...scope,
			...rest,
			ref
		});
		$[3] = ref;
		$[4] = rest;
		$[5] = scope;
		$[6] = t1;
	} else t1 = $[6];
	return t1;
});
AssistantModalPrimitiveTrigger.displayName = "AssistantModalPrimitive.Trigger";
//#endregion
export { AssistantModalPrimitiveTrigger };
