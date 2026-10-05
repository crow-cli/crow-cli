"use client";
import { useTriggerBehaviorRegistration } from "./TriggerPopover.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useEffect, useInsertionEffect, useRef } from "@assistant-ui/tap/react-shim";
import { unstable_defaultDirectiveFormatter } from "@assistant-ui/core";
//#region src/primitives/composer/trigger/TriggerPopoverDirective.tsx
/**
* Configures a `<TriggerPopover>` to insert a directive chip when an item is
* selected. Render exactly one behavior sub-primitive per `<TriggerPopover>`.
*
* Exposed as `ComposerPrimitive.Unstable_TriggerPopover.Directive`.
*
* @example
* ```tsx
* <ComposerPrimitive.Unstable_TriggerPopover char="@" adapter={mentionAdapter}>
*   <ComposerPrimitive.Unstable_TriggerPopover.Directive
*     formatter={unstable_defaultDirectiveFormatter}
*     onInserted={(item) => track("mention", item.id)}
*   />
* </ComposerPrimitive.Unstable_TriggerPopover>
* ```
*/
const ComposerPrimitiveTriggerPopoverDirective = (t0) => {
	const $ = c(7);
	const { formatter, onInserted } = t0;
	const { register } = useTriggerBehaviorRegistration();
	const onInsertedRef = useRef(onInserted);
	let t1;
	let t2;
	if ($[0] !== onInserted) {
		t1 = () => {
			onInsertedRef.current = onInserted;
		};
		t2 = [onInserted];
		$[0] = onInserted;
		$[1] = t1;
		$[2] = t2;
	} else {
		t1 = $[1];
		t2 = $[2];
	}
	useInsertionEffect(t1, t2);
	let t3;
	let t4;
	if ($[3] !== formatter || $[4] !== register) {
		t3 = () => {
			return register({
				kind: "directive",
				formatter: formatter ?? unstable_defaultDirectiveFormatter,
				onInserted: (item) => onInsertedRef.current?.(item)
			});
		};
		t4 = [register, formatter];
		$[3] = formatter;
		$[4] = register;
		$[5] = t3;
		$[6] = t4;
	} else {
		t3 = $[5];
		t4 = $[6];
	}
	useEffect(t3, t4);
	return null;
};
ComposerPrimitiveTriggerPopoverDirective.displayName = "ComposerPrimitive.TriggerPopoverDirective";
//#endregion
export { ComposerPrimitiveTriggerPopoverDirective };
