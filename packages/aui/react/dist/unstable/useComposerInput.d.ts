import type { ComposerSendOptions } from "@assistant-ui/core/store";
import { type TriggerPopoverAriaProps } from "../primitives/composer/useComposerInputState.js";
export type Unstable_UseComposerInputOptions = {
    /**
     * Disables the input in addition to the composer's own disabled sources
     * (thread disabled, active dictation). When disabled, `isDisabled` is `true`
     * and `canSend` is `false`.
     */
    disabled?: boolean | undefined;
};
export type Unstable_ComposerInput = {
    /** Current composer text, or `""` when the composer is not editing. */
    value: string;
    /**
     * Writes `text` into the composer, mirroring `ComposerPrimitive.Input`:
     * a no-op unless the composer is editing; the controlled value stays in
     * sync within the same tick.
     */
    setText(text: string): void;
    /**
     * Sends the current message when `canSend` is `true`; otherwise a no-op.
     * Accepts the same options as the composer send action.
     */
    send(options?: ComposerSendOptions): void;
    /**
     * Whether the input is disabled, combining the `disabled` option with the
     * composer's own disabled sources (thread disabled, active dictation).
     */
    isDisabled: boolean;
    /**
     * Whether a send is currently available. Matches `ComposerPrimitive.Send`
     * gating (non-empty editing composer, not running without queue support) and
     * is additionally `false` while `isDisabled`.
     */
    canSend: boolean;
};
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
export declare function unstable_useComposerInput(options?: Unstable_UseComposerInputOptions): Unstable_ComposerInput;
export type Unstable_TriggerPopoverAriaProps = TriggerPopoverAriaProps;
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
export declare function unstable_useTriggerPopoverAriaProps(): Unstable_TriggerPopoverAriaProps;