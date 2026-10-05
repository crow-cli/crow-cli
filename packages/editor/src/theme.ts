/**
 * CodeMirror theming, lifted from haklex `packages/cm-editor/src/theme.ts`:
 * oneDark for dark, the default highlight style for light, and a base theme
 * that keeps the editor transparent so the app's own tokens show through.
 */
import { defaultHighlightStyle, syntaxHighlighting } from "@codemirror/language";
import type { Extension } from "@codemirror/state";
import { oneDark } from "@codemirror/theme-one-dark";
import { EditorView } from "@codemirror/view";

/** What a component that only knows light from dark can consume. */
export type ColorScheme = "light" | "dark";

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

export function getThemeExtensions(colorScheme: "light" | "dark"): Extension {
  return colorScheme === "dark"
    ? [oneDark, baseTheme]
    : [baseTheme, syntaxHighlighting(defaultHighlightStyle, { fallback: true })];
}
