"use client";
import { useTriggerBehaviorRegistration } from "./TriggerPopover.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useEffect, useInsertionEffect, useRef } from "@assistant-ui/tap/react-shim";
import { unstable_defaultDirectiveFormatter } from "@assistant-ui/core";
//#region src/primitives/composer/trigger/TriggerPopoverAction.tsx
/**
* Configures a `<TriggerPopover>` to fire a handler when an item is selected,
* optionally leaving a directive chip behind as an audit trail. Render exactly
* one behavior sub-primitive per `<TriggerPopover>`.
*
* Exposed as `ComposerPrimitive.Unstable_TriggerPopover.Action`.
*
* @example
* ```tsx
* <ComposerPrimitive.Unstable_TriggerPopover char="/" adapter={slashAdapter}>
*   <ComposerPrimitive.Unstable_TriggerPopover.Action
*     onExecute={(item) => commandHandlers[item.id]?.()}
*     removeOnExecute={false}
*   />
* </ComposerPrimitive.Unstable_TriggerPopover>
* ```
*/
const ComposerPrimitiveTriggerPopoverAction = (t0) => {
	const $ = c(8);
	const { formatter, onExecute, removeOnExecute } = t0;
	const { register } = useTriggerBehaviorRegistration();
	const onExecuteRef = useRef(onExecute);
	let t1;
	let t2;
	if ($[0] !== onExecute) {
		t1 = () => {
			onExecuteRef.current = onExecute;
		};
		t2 = [onExecute];
		$[0] = onExecute;
		$[1] = t1;
		$[2] = t2;
	} else {
		t1 = $[1];
		t2 = $[2];
	}
	useInsertionEffect(t1, t2);
	let t3;
	let t4;
	if ($[3] !== formatter || $[4] !== register || $[5] !== removeOnExecute) {
		t3 = () => {
			const behavior = {
				kind: "action",
				formatter: formatter ?? unstable_defaultDirectiveFormatter,
				onExecute: (item) => onExecuteRef.current(item),
				...removeOnExecute !== void 0 ? { removeOnExecute } : {}
			};
			return register(behavior);
		};
		t4 = [
			register,
			formatter,
			removeOnExecute
		];
		$[3] = formatter;
		$[4] = register;
		$[5] = removeOnExecute;
		$[6] = t3;
		$[7] = t4;
	} else {
		t3 = $[6];
		t4 = $[7];
	}
	useEffect(t3, t4);
	return null;
};
ComposerPrimitiveTriggerPopoverAction.displayName = "ComposerPrimitive.TriggerPopoverAction";
//#endregion
export { ComposerPrimitiveTriggerPopoverAction };
