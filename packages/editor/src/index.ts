/**
 * The CodeMirror 6 editor, lifted from haklex `rich-ext-code-snippet` (its
 * CodeEditorModal's EditorView setup minus the lexical decorator and the
 * dnd-kit chrome). A package of its own so the chat app stays a consumer:
 * the editor knows CodeMirror and nothing else.
 */
export { CodeEditor, type CodeEditorProps } from "./code-editor";
export {
  languageOfPath,
  normalizeLanguage,
  languageAliases,
  getLanguageCandidates,
  loadLanguageExtension,
} from "./language";
export { baseTheme, editorTheme, highlightStyle } from "./theme";
