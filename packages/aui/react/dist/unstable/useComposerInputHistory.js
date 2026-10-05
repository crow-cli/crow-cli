"use client";
import { useTriggerPopoverRootContextOptional } from "../primitives/composer/trigger/TriggerPopoverRootContext.js";
import { useCallback, useEffect, useMemo, useRef } from "@assistant-ui/tap/react-shim";
import { useAui } from "@assistant-ui/store";
import { flushTapSync } from "@assistant-ui/tap";
import { getThreadMessageText } from "@assistant-ui/core/internal";
//#region src/unstable/useComposerInputHistory.ts
const deriveHistory = (messages) => {
	const entries = [];
	for (let i = messages.length - 1; i >= 0; i--) {
		const message = messages[i];
		if (message.role !== "user") continue;
		const text = getThreadMessageText(message).trim();
		if (!text) continue;
		if (entries[entries.length - 1] === text) continue;
		entries.push(text);
	}
	return entries;
};
const isOnFirstLine = (value, caret) => !value.slice(0, caret).includes("\n");
const isOnLastLine = (value, caret) => !value.slice(caret).includes("\n");
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
function unstable_useComposerInputHistory() {
	const aui = useAui();
	const popoverCtx = useTriggerPopoverRootContextOptional();
	const browseRef = useRef(null);
	useEffect(() => {
		if (aui.composer.getState().type !== "thread") return void 0;
		return aui.on("threads.selectionChanged", () => {
			browseRef.current = null;
		});
	}, [aui]);
	const onKeyDown = useCallback((e) => {
		if (e.defaultPrevented) return;
		if (e.key !== "ArrowUp" && e.key !== "ArrowDown") return;
		if (e.nativeEvent.isComposing) return;
		if (e.shiftKey || e.ctrlKey || e.metaKey || e.altKey) return;
		if (popoverCtx && popoverCtx.getActiveAria() !== null) return;
		if (aui.composer.getState().type !== "thread") return;
		const textarea = e.currentTarget;
		const { selectionStart, selectionEnd, value } = textarea;
		if (selectionStart !== selectionEnd) return;
		if (browseRef.current && value !== browseRef.current.lastRecalledText) browseRef.current = null;
		const browse = browseRef.current;
		const commitText = (text) => {
			flushTapSync(() => aui.composer.setText(text));
			requestAnimationFrame(() => {
				textarea.setSelectionRange(text.length, text.length);
			});
			e.preventDefault();
		};
		const recall = (history, cursor, draftSnapshot) => {
			const entry = history[cursor];
			if (entry === void 0) {
				e.preventDefault();
				return;
			}
			browseRef.current = {
				cursor,
				draftSnapshot,
				lastRecalledText: entry
			};
			commitText(entry);
		};
		if (e.key === "ArrowUp") {
			if (!isOnFirstLine(value, selectionStart)) return;
			if (!browse) {
				if (value.trim() !== "") return;
				const history = deriveHistory(aui.thread.getState().messages);
				if (history.length === 0) return;
				recall(history, 0, value);
				return;
			}
			const history = deriveHistory(aui.thread.getState().messages);
			const next = browse.cursor + 1;
			if (next >= history.length) {
				e.preventDefault();
				return;
			}
			recall(history, next, browse.draftSnapshot);
			return;
		}
		if (!browse) return;
		if (!isOnLastLine(value, selectionEnd)) return;
		const next = browse.cursor - 1;
		if (next < 0) {
			browseRef.current = null;
			commitText(browse.draftSnapshot);
			return;
		}
		recall(deriveHistory(aui.thread.getState().messages), next, browse.draftSnapshot);
	}, [aui, popoverCtx]);
	return useMemo(() => ({ onKeyDown }), [onKeyDown]);
}
//#endregion
export { unstable_useComposerInputHistory };
