//#region src/primitives/composer/trigger/detectTrigger.ts
const WHITESPACE_RE = /\s/u;
function resolveTriggerMatch(text, triggerChar, cursorPosition, match) {
	if (match === null) return null;
	const { query, offset, endOffset } = match;
	if (offset < 0 || offset + triggerChar.length > cursorPosition) return null;
	if (!text.startsWith(triggerChar, offset)) return null;
	if (endOffset < offset + triggerChar.length || endOffset > text.length) return null;
	return {
		query,
		offset,
		endOffset
	};
}
/**
* Detect a trigger character in text relative to the cursor position.
*
* @internal Exported for testing and for trigger resources.
*/
function detectTrigger(text, triggerChar, cursorPosition, matcher) {
	if (matcher) return resolveTriggerMatch(text, triggerChar, cursorPosition, matcher(text, triggerChar, cursorPosition));
	const textUpToCursor = text.slice(0, cursorPosition);
	for (let i = textUpToCursor.length - 1; i >= 0; i--) {
		const char = textUpToCursor[i];
		if (WHITESPACE_RE.test(char)) return null;
		if (textUpToCursor.startsWith(triggerChar, i)) {
			if (i > 0 && !WHITESPACE_RE.test(textUpToCursor[i - 1])) continue;
			return {
				query: textUpToCursor.slice(i + triggerChar.length),
				offset: i,
				endOffset: cursorPosition
			};
		}
	}
	return null;
}
//#endregion
export { detectTrigger, resolveTriggerMatch };
