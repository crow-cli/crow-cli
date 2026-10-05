/**
 * CodeMirror theming for crow's editor pane.
 *
 * The chrome (background, gutters, selection, caret) reads the app's semantic
 * tokens, and the syntax palette reads the `--code-*` variables each theme CSS
 * publishes. That means the editor follows the theme dropdown — latte, mocha,
 * macchiato, and anything added later — with no per-theme code here: `var()`
 * re-resolves live when `<html data-theme>` changes, so there is nothing to
 * reconfigure on a theme switch.
 */
import { HighlightStyle, syntaxHighlighting } from "@codemirror/language";
import type { Extension } from "@codemirror/state";
import { tags } from "@lezer/highlight";
import { EditorView } from "@codemirror/view";

const token = (name: string) => `var(--code-${name})`;

export const baseTheme: Extension = EditorView.theme({
  "&": {
    backgroundColor: "transparent",
    height: "100%",
    fontSize: "13px",
  },
  "&.cm-editor": { outline: "none" },
  "&.cm-editor.cm-focused": { outline: "none" },
  ".cm-scroller": {
    overflow: "auto",
    fontFamily: "var(--font-mono, ui-monospace, SFMono-Regular, Menlo, monospace)",
    lineHeight: "1.6",
  },
  ".cm-content": {
    caretColor: "var(--foreground)",
    padding: "8px 0",
  },
  ".cm-gutters": {
    backgroundColor: "transparent",
    color: "var(--muted-foreground)",
    border: "none",
    borderRight: "1px solid var(--border)",
    paddingRight: "8px",
  },
  ".cm-lineNumbers .cm-gutterElement": { padding: "0 8px 0 12px" },
  ".cm-activeLine": { backgroundColor: "color-mix(in oklab, var(--muted) 40%, transparent)" },
  ".cm-activeLineGutter": {
    backgroundColor: "transparent",
    color: "var(--foreground)",
  },
  ".cm-selectionBackground": { backgroundColor: "rgba(125, 125, 125, 0.26) !important" },
  "&.cm-focused .cm-selectionBackground": {
    backgroundColor: "rgba(125, 125, 125, 0.34) !important",
  },
  ".cm-cursor": { borderLeftColor: "var(--foreground)" },
  // A wrapped logical line stays one gutter number; the indent guides make the
  // continuation rows readable.
  ".cm-line": { padding: "0 12px" },
});

/**
 * The token palette, mirrored from the Prism theme in
 * `packages/chat/src/lib/syntax-highlighter.tsx` so a code fence and an editor
 * buffer look the same in the same theme.
 */
export const highlightStyle: HighlightStyle = HighlightStyle.define([
  { tag: [tags.comment, tags.lineComment, tags.blockComment, tags.meta, tags.documentMeta, tags.annotation, tags.processingInstruction], color: token("comment") },
  { tag: tags.docComment, color: token("comment"), fontStyle: "italic" },
  { tag: [tags.string, tags.docString, tags.character, tags.attributeValue, tags.regexp, tags.escape, tags.color, tags.url, tags.special(tags.string)], color: token("string") },
  { tag: [tags.number, tags.integer, tags.float, tags.bool, tags.null, tags.atom, tags.unit, tags.literal], color: token("number") },
  { tag: [tags.keyword, tags.self, tags.modifier, tags.operatorKeyword, tags.controlKeyword, tags.definitionKeyword, tags.moduleKeyword], color: token("keyword") },
  { tag: [tags.operator, tags.derefOperator, tags.arithmeticOperator, tags.logicOperator, tags.bitwiseOperator, tags.compareOperator, tags.updateOperator, tags.definitionOperator, tags.typeOperator, tags.controlOperator], color: token("operator") },
  { tag: [tags.punctuation, tags.separator, tags.bracket, tags.angleBracket, tags.squareBracket, tags.paren, tags.brace, tags.contentSeparator], color: token("punctuation") },
  { tag: [tags.propertyName, tags.definition(tags.propertyName)], color: token("property") },
  { tag: [tags.typeName, tags.tagName, tags.className, tags.namespace, tags.macroName], color: token("type") },
  { tag: [tags.function(tags.variableName), tags.function(tags.propertyName)], color: token("function") },
  { tag: tags.attributeName, color: token("attr") },
  { tag: [tags.variableName, tags.definition(tags.variableName), tags.labelName, tags.constant(tags.variableName)], color: token("property") },
  { tag: tags.inserted, color: token("inserted") },
  { tag: [tags.deleted, tags.changed, tags.invalid], color: token("deleted") },
]);

/** The one editor extension set: chrome + token palette, all theme-driven. */
export const editorTheme: Extension = [
  baseTheme,
  syntaxHighlighting(highlightStyle, { fallback: true }),
];
