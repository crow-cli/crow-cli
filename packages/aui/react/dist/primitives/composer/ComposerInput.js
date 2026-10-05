"use client";
import { renderSlot } from "../../utils/Primitive.js";
import { useComposerCompactContextOptional } from "./ComposerCompactContext.js";
import { useOnScrollToBottom } from "../../utils/hooks/useOnScrollToBottom.js";
import { useMediaQuery } from "../../utils/hooks/useMediaQuery.js";
import { isCompositionKey } from "../../utils/isCompositionKey.js";
import { useComposerInputPluginRegistryOptional } from "./ComposerInputPluginContext.js";
import { useComposerInputDisabled, useComposerInputValue, useTriggerPopoverAriaProps } from "./useComposerInputState.js";
import { forwardRef, isValidElement, useCallback, useEffect, useRef } from "@assistant-ui/tap/react-shim";
import { useAui } from "@assistant-ui/store";
import { flushTapSync } from "@assistant-ui/tap";
import { jsx } from "react/jsx-runtime";
import { composeEventHandlers, useComposedRefs, useEscapeKeydown } from "radix-ui/internal";
import { Slot } from "radix-ui";
import TextareaAutosize from "react-textarea-autosize";
//#region src/primitives/composer/ComposerInput.tsx
const TOUCH_PRIMARY_QUERY = "(pointer: coarse) and (not (any-pointer: fine))";
/**
* A text input component for composing messages.
*
* This component provides a rich text input experience with automatic resizing,
* keyboard shortcuts, file paste support, and intelligent focus management.
* It integrates with the composer context to manage message state and submission.
*
* When rendered inside `Unstable_TriggerPopoverRoot` and a popover is open, the
* underlying `<textarea>` automatically receives `aria-controls`,
* `aria-expanded`, `aria-haspopup`, and `aria-activedescendant` for the
* combobox relationship. These computed attributes override user-provided
* values for those four ARIA props while the popover is open.
*
* @example
* ```tsx
* // Ctrl/Cmd+Enter to submit (plain Enter inserts newline)
* <ComposerPrimitive.Input
*   placeholder="Type your message..."
*   submitMode="ctrlEnter"
* />
*
* // Insert a newline on Enter on touch-primary devices.
* <ComposerPrimitive.Input
*   placeholder="Type your message..."
*   unstable_insertNewlineOnTouchEnter
* />
*
* // Old API (deprecated, still supported)
* <ComposerPrimitive.Input
*   placeholder="Type your message..."
*   submitOnEnter={true}
* />
* ```
*/
const ComposerPrimitiveInput = forwardRef(({ autoFocus = false, asChild, render, disabled: disabledProp, onChange, onKeyDown, onPaste, onSelect, submitOnEnter, submitMode, cancelOnEscape = true, unstable_focusOnRunStart = true, unstable_focusOnScrollToBottom = true, unstable_focusOnThreadSwitched = true, unstable_insertNewlineOnTouchEnter = false, addAttachmentOnPaste = true, onHeightChange, ...rest }, forwardedRef) => {
	const aui = useAui();
	const pluginRegistry = useComposerInputPluginRegistryOptional();
	const compactContext = useComposerCompactContextOptional();
	const declaredSubmitMode = submitMode ?? (submitOnEnter === false ? "none" : "enter");
	const isTouchPrimary = useMediaQuery(unstable_insertNewlineOnTouchEnter ? TOUCH_PRIMARY_QUERY : null);
	const effectiveSubmitMode = unstable_insertNewlineOnTouchEnter && isTouchPrimary && declaredSubmitMode === "enter" ? "none" : declaredSubmitMode;
	const value = useComposerInputValue();
	const isDisabled = useComposerInputDisabled(disabledProp);
	const textareaRef = useRef(null);
	const ref = useComposedRefs(forwardedRef, textareaRef);
	const compositionRef = useRef(false);
	useEscapeKeydown((e) => {
		if (!textareaRef.current?.contains(e.target)) return;
		if (isCompositionKey(e)) return;
		if (pluginRegistry) {
			for (const plugin of pluginRegistry.getPlugins()) if (plugin.handleKeyDown(e)) return;
		}
		if (!cancelOnEscape) return;
		const composer = aui.composer;
		if (composer.getState().canCancel) {
			composer.cancel();
			e.preventDefault();
		}
	});
	const handleKeyPress = (e_0) => {
		if (isDisabled) return;
		if (isCompositionKey(e_0.nativeEvent)) return;
		if (pluginRegistry) {
			for (const plugin_0 of pluginRegistry.getPlugins()) if (plugin_0.handleKeyDown(e_0)) return;
		}
		if (e_0.key === "Enter") {
			const threadState = aui.thread.getState();
			const hasQueue = threadState.capabilities.queue;
			if (e_0.shiftKey && (e_0.ctrlKey || e_0.metaKey) && hasQueue && declaredSubmitMode !== "none" && aui.composer.getState().canSend) {
				e_0.preventDefault();
				aui.composer.send({ steer: true });
				return;
			}
			if (e_0.shiftKey) return;
			if (threadState.isRunning && !hasQueue && threadState.voice === void 0) return;
			let shouldSubmit = false;
			if (effectiveSubmitMode === "ctrlEnter") shouldSubmit = e_0.ctrlKey || e_0.metaKey;
			else if (effectiveSubmitMode === "enter") shouldSubmit = true;
			if (shouldSubmit) {
				e_0.preventDefault();
				textareaRef.current?.closest("form")?.requestSubmit();
			}
		}
	};
	const handlePaste = async (e_1) => {
		if (!addAttachmentOnPaste) return;
		const threadCapabilities = aui.thread.getState().capabilities;
		const files = Array.from(e_1.clipboardData?.files || []);
		if (threadCapabilities.attachments && files.length > 0) {
			e_1.preventDefault();
			await Promise.all(files.map(async (file) => {
				try {
					await aui.composer.addAttachment(file);
				} catch {}
			}));
		}
	};
	const handleHeightChange = (height, meta) => {
		onHeightChange?.(height, meta);
		if (!compactContext) return;
		const el = textareaRef.current;
		if (!el || el.value === "") return;
		const cs = getComputedStyle(el);
		const contentHeight = cs.boxSizing === "border-box" ? height - parseFloat(cs.paddingTop) - parseFloat(cs.paddingBottom) - parseFloat(cs.borderTopWidth) - parseFloat(cs.borderBottomWidth) : height;
		if (Math.round(contentHeight / meta.rowHeight) > 1) compactContext.setMultiline(true);
	};
	const autoFocusEnabled = autoFocus && !isDisabled;
	const focus = useCallback(() => {
		const textarea = textareaRef.current;
		if (!textarea || !autoFocusEnabled) return;
		textarea.focus({ preventScroll: true });
		textarea.setSelectionRange(textarea.value.length, textarea.value.length);
	}, [autoFocusEnabled]);
	useEffect(() => focus(), [focus]);
	useOnScrollToBottom(() => {
		if (aui.composer.getState().type === "thread" && unstable_focusOnScrollToBottom) focus();
	});
	useEffect(() => {
		if (aui.composer.getState().type !== "thread" || !unstable_focusOnRunStart) return void 0;
		return aui.on("thread.runStart", focus);
	}, [
		unstable_focusOnRunStart,
		focus,
		aui
	]);
	useEffect(() => {
		if (aui.composer.getState().type !== "thread" || !unstable_focusOnThreadSwitched) return void 0;
		return aui.on("threads.selectionChanged", focus);
	}, [
		unstable_focusOnThreadSwitched,
		focus,
		aui
	]);
	useEffect(() => {
		if (value === "") compactContext?.setMultiline(false);
	}, [value, compactContext]);
	const ariaComboboxProps = useTriggerPopoverAriaProps();
	const inputProps = {
		name: "input",
		value,
		...rest,
		...ariaComboboxProps,
		ref,
		disabled: isDisabled,
		onChange: composeEventHandlers(onChange, (e_2) => {
			if (!aui.composer.getState().isEditing) return;
			const nativeIsComposing = e_2.nativeEvent.isComposing === true;
			if (compositionRef.current && !nativeIsComposing) compositionRef.current = false;
			const isComposing = nativeIsComposing || compositionRef.current;
			flushTapSync(() => {
				aui.composer.setText(e_2.target.value);
			});
			if (isComposing) return;
			const pos = e_2.target.selectionStart ?? e_2.target.value.length;
			if (pluginRegistry) for (const plugin_1 of pluginRegistry.getPlugins()) plugin_1.setCursorPosition(pos);
		}),
		onKeyDown: composeEventHandlers(onKeyDown, handleKeyPress),
		onCompositionStart: composeEventHandlers(rest.onCompositionStart, () => {
			compositionRef.current = true;
		}),
		onCompositionEnd: composeEventHandlers(rest.onCompositionEnd, (e_3) => {
			compositionRef.current = false;
			if (!aui.composer.getState().isEditing) return;
			const target = e_3.target;
			flushTapSync(() => {
				aui.composer.setText(target.value);
			});
			const pos_0 = target.selectionStart ?? target.value.length;
			if (pluginRegistry) for (const plugin_2 of pluginRegistry.getPlugins()) plugin_2.setCursorPosition(pos_0);
		}),
		onSelect: composeEventHandlers(onSelect, (e_4) => {
			if (compositionRef.current) return;
			const target_0 = e_4.target;
			const pos_1 = target_0.selectionStart ?? target_0.value.length;
			if (pluginRegistry) for (const plugin_3 of pluginRegistry.getPlugins()) plugin_3.setCursorPosition(pos_1);
		}),
		onPaste: composeEventHandlers(onPaste, handlePaste),
		...compactContext ? { onHeightChange: handleHeightChange } : onHeightChange !== void 0 ? { onHeightChange } : {}
	};
	if (render && isValidElement(render)) return renderSlot(render, rest.children, inputProps);
	const Component = asChild ? Slot.Root : TextareaAutosize;
	return /* @__PURE__ */ jsx(Component, { ...inputProps });
});
ComposerPrimitiveInput.displayName = "ComposerPrimitive.Input";
//#endregion
export { ComposerPrimitiveInput };
