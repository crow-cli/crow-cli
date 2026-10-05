export type TriggerMatch = {
    readonly query: string;
    readonly offset: number;
    readonly endOffset: number;
};
/**
 * Locates a trigger query in `text` relative to `cursorPosition`.
 *
 * `offset` is the index of `triggerChar`. `endOffset` is the exclusive end of
 * the span both the textarea and Lexical replace on select. `query` is the
 * search string and may differ from that span.
 *
 * Return null when the caret is at or before the trigger. Escape moves the
 * caret to `offset` so a match there would reopen the popover.
 */
export type TriggerMatcher = (text: string, triggerChar: string, cursorPosition: number) => TriggerMatch | null;
export declare function resolveTriggerMatch(text: string, triggerChar: string, cursorPosition: number, match: TriggerMatch | null): TriggerMatch | null;