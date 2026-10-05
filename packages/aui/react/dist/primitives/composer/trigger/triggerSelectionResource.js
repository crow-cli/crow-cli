import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useEffectEvent, useRef } from "@assistant-ui/tap/react-shim";
import { resource } from "@assistant-ui/tap";
//#region src/primitives/composer/trigger/triggerSelectionResource.ts
/** Owns composer text mutation + behavior dispatch on item selection. */
const useTriggerSelectionResource = (t0) => {
	const $ = c(15);
	const { behavior, trigger, aui, setCursorPosition, onSelected } = t0;
	const selectItemOverrideRef = useRef(null);
	let t1;
	if ($[0] === Symbol.for("react.memo_cache_sentinel")) {
		t1 = (fn) => {
			selectItemOverrideRef.current = fn;
			return () => {
				if (selectItemOverrideRef.current === fn) selectItemOverrideRef.current = null;
			};
		};
		$[0] = t1;
	} else t1 = $[0];
	const registerSelectItemOverride = useEffectEvent(t1);
	let t2;
	if ($[1] !== aui || $[2] !== behavior || $[3] !== onSelected || $[4] !== setCursorPosition || $[5] !== trigger) {
		t2 = (item) => {
			if (!trigger || !behavior) return;
			if (selectItemOverrideRef.current?.(item)) {
				onSelected();
				return;
			}
			const currentText = aui.composer.getState().text;
			const before = currentText.slice(0, trigger.offset);
			const after = currentText.slice(trigger.endOffset);
			const insertDirective = () => {
				const directive = behavior.formatter.serialize(item);
				aui.composer.setText(before + directive + (after.startsWith(" ") ? after : ` ${after}`));
				setCursorPosition(before.length + directive.length + 1);
			};
			if (behavior.kind === "directive") {
				insertDirective();
				behavior.onInserted?.(item);
			} else {
				if (behavior.removeOnExecute) {
					aui.composer.setText(before + (after.startsWith(" ") ? after.slice(1) : after));
					setCursorPosition(before.length);
				} else insertDirective();
				behavior.onExecute(item);
			}
			onSelected();
		};
		$[1] = aui;
		$[2] = behavior;
		$[3] = onSelected;
		$[4] = setCursorPosition;
		$[5] = trigger;
		$[6] = t2;
	} else t2 = $[6];
	const selectItem = useEffectEvent(t2);
	let t3;
	if ($[7] !== onSelected || $[8] !== setCursorPosition || $[9] !== trigger) {
		t3 = () => {
			onSelected();
			if (trigger) setCursorPosition(trigger.offset);
		};
		$[7] = onSelected;
		$[8] = setCursorPosition;
		$[9] = trigger;
		$[10] = t3;
	} else t3 = $[10];
	const close = useEffectEvent(t3);
	let t4;
	if ($[11] !== close || $[12] !== registerSelectItemOverride || $[13] !== selectItem) {
		t4 = {
			selectItem,
			close,
			registerSelectItemOverride
		};
		$[11] = close;
		$[12] = registerSelectItemOverride;
		$[13] = selectItem;
		$[14] = t4;
	} else t4 = $[14];
	return t4;
};
const TriggerSelectionResource = resource(useTriggerSelectionResource);
//#endregion
export { TriggerSelectionResource };
