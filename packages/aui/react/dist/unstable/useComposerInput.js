"use client";
import { useComposerInputDisabled, useComposerInputValue, useTriggerPopoverAriaProps } from "../primitives/composer/useComposerInputState.js";
import { useComposerSend } from "@assistant-ui/core/react";
import { useCallback } from "@assistant-ui/tap/react-shim";
import { useAui } from "@assistant-ui/store";
import { flushTapSync } from "@assistant-ui/tap";
//#region src/unstable/useComposerInput.ts
/**
* @deprecated Under active development and might change without notice.
*
* Headless bridge to the composer's text value and send action, for building a
* custom composer input without `ComposerPrimitive.Input`. It is a thin bridge,
* not a second input: it does not own keyboard behavior, autosize, IME or
* contentEditable sync, paste/drop attachments, focus management, or rich-text
* state. Spread `unstable_useTriggerPopoverAriaProps()` onto your element for
* trigger-popover combobox semantics.
*
* @example
* ```tsx
* const { value, setText, send, isDisabled, canSend } = unstable_useComposerInput();
* <textarea
*   value={value}
*   disabled={isDisabled}
*   onChange={(e) => setText(e.target.value)}
*   onKeyDown={(e) => {
*     if (e.key === "Enter" && !e.shiftKey && canSend) {
*       e.preventDefault();
*       send();
*     }
*   }}
* />
* ```
*/
function unstable_useComposerInput(options) {
	const aui = useAui();
	const value = useComposerInputValue();
	const isDisabled = useComposerInputDisabled(options?.disabled);
	const setText = useCallback((text) => {
		if (!aui.composer.getState().isEditing) return;
		flushTapSync(() => {
			aui.composer.setText(text);
		});
	}, [aui]);
	const { send: rawSend, disabled: sendDisabled } = useComposerSend();
	const canSend = !sendDisabled && !isDisabled;
	return {
		value,
		setText,
		send: useCallback((sendOptions) => {
			if (!canSend) return;
			rawSend(sendOptions);
		}, [canSend, rawSend]),
		isDisabled,
		canSend
	};
}
/**
* @deprecated Under active development and might change without notice.
*
* ARIA combobox attributes for the focused element (typically the composer
* input) describing the open trigger popover, per the WAI-ARIA editable
* combobox pattern. Returns an empty object outside a `TriggerPopoverRoot` or
* when no popover is open. Spread these last so they take precedence over any
* matching ARIA props you set yourself, mirroring `ComposerPrimitive.Input`.
*
* @example
* ```tsx
* const aria = unstable_useTriggerPopoverAriaProps();
* <textarea {...aria} />
* ```
*/
function unstable_useTriggerPopoverAriaProps() {
	return useTriggerPopoverAriaProps();
}
//#endregion
export { unstable_useComposerInput, unstable_useTriggerPopoverAriaProps };
