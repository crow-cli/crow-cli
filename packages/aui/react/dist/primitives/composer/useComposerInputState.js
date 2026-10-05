"use client";
import { useTriggerPopoverActiveAriaOptional } from "./trigger/TriggerPopoverRootContext.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useAuiState } from "@assistant-ui/store";
//#region src/primitives/composer/useComposerInputState.ts
function useComposerInputValue() {
	return useAuiState(_temp);
}
function _temp(s) {
	return s.composer.isEditing ? s.composer.text : "";
}
function useComposerInputDisabled(disabled) {
	const composerDisabled = useAuiState(_temp2);
	return Boolean(composerDisabled) || Boolean(disabled);
}
function _temp2(s) {
	return s.thread.isDisabled || s.composer.dictation?.inputDisabled;
}
function useTriggerPopoverAriaProps() {
	const $ = c(4);
	const activeAria = useTriggerPopoverActiveAriaOptional();
	if (!activeAria) {
		let t0;
		if ($[0] === Symbol.for("react.memo_cache_sentinel")) {
			t0 = {};
			$[0] = t0;
		} else t0 = $[0];
		return t0;
	}
	let t0;
	if ($[1] !== activeAria.highlightedItemId || $[2] !== activeAria.popoverId) {
		t0 = {
			"aria-controls": activeAria.popoverId,
			"aria-expanded": true,
			"aria-haspopup": "listbox",
			"aria-activedescendant": activeAria.highlightedItemId
		};
		$[1] = activeAria.highlightedItemId;
		$[2] = activeAria.popoverId;
		$[3] = t0;
	} else t0 = $[3];
	return t0;
}
//#endregion
export { useComposerInputDisabled, useComposerInputValue, useTriggerPopoverAriaProps };
