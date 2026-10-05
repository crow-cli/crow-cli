import { type KeyboardEventHandler } from "react";
export type Unstable_ComposerInputHistory = {
    /** Keydown handler to spread onto `ComposerPrimitive.Input`. */
    onKeyDown: KeyboardEventHandler<HTMLTextAreaElement>;
};
/**
 * @deprecated Under active development and might change without notice.
 *
 * Terminal-style input history for the thread composer: ArrowUp on an
 * empty draft recalls previously sent user messages (newest first),
 * ArrowDown steps back toward the newest and finally restores the draft
 * that was being typed when browsing started.
 *
 * Recall only triggers when the caret is on the first/last line with no
 * selection, so multi-line editing keeps native arrow behavior. The
 * handler yields to an open mention/slash popover, to IME composition,
 * to modifier keys, and to consumer handlers that already called
 * `preventDefault`. It is inert on edit composers.
 *
 * @example
 * ```tsx
 * const history = unstable_useComposerInputHistory();
 * <ComposerPrimitive.Input {...history} />
 * ```
 */
export declare function unstable_useComposerInputHistory(): Unstable_ComposerInputHistory;