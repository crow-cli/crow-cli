/**
 * The code editor: CodeMirror 6, lifted out of haklex's
 * `rich-ext-code-snippet` (whose CodeEditorModal is this same EditorView setup
 * wrapped in a dnd-kit file sidebar and vanilla-extract styles).
 *
 * It is deliberately not a controlled component. CodeMirror owns the document
 * while you type; React hands it a new one only when `rev` moves, which the
 * store bumps solely for changes that came from somewhere else.
 *
 * The theme is `editorTheme`, driven entirely by the app's CSS variables, so
 * switching the app theme recolors the editor without a reconfigure.
 */
import { defaultKeymap, history, historyKeymap, indentWithTab } from "@codemirror/commands";
import { Compartment, EditorState } from "@codemirror/state";
import {
  drawSelection,
  EditorView,
  highlightActiveLine,
  highlightActiveLineGutter,
  keymap,
  lineNumbers,
} from "@codemirror/view";
import { useEffect, useRef } from "react";
import { loadLanguageExtension, normalizeLanguage } from "./language";
import { editorTheme } from "./theme";

export type CodeEditorProps = {
  language: string;
  /** The buffer's content. */
  value: string;
  /** Moves only when the content changed somewhere other than this editor. */
  rev: number;
  onChange: (content: string) => void;
  onSave: () => void;
};

export function CodeEditor({ language, value, rev, onChange, onSave }: CodeEditorProps) {
  const host = useRef<HTMLDivElement>(null);
  const view = useRef<EditorView | null>(null);
  const langSlot = useRef(new Compartment());
  // What CodeMirror holds, so an echo of our own write can be told apart from
  // somebody else's without asking the store.
  const doc = useRef(value);
  const initial = useRef({ value });
  const change = useRef(onChange);
  const save = useRef(onSave);
  change.current = onChange;
  save.current = onSave;

  // One editor per mount. The tab strip keys this component by path, so
  // switching tabs remounts it and the initial doc is the whole input.
  useEffect(() => {
    const parent = host.current;
    if (!parent) return;
    doc.current = initial.current.value;
    const editor = new EditorView({
      parent,
      state: EditorState.create({
        doc: doc.current,
        extensions: [
          history(),
          keymap.of([
            // Ctrl+S commits to the server; the browser's save dialog never
            // gets a say.
            {
              key: "Mod-s",
              preventDefault: true,
              run: () => {
                save.current();
                return true;
              },
            },
            ...defaultKeymap,
            ...historyKeymap,
            indentWithTab,
          ]),
          EditorView.updateListener.of((update) => {
            if (!update.docChanged) return;
            const text = update.state.doc.toString();
            doc.current = text;
            change.current(text);
          }),
          // Word wrap: a 200-column line stays inside the pane, and the gutter
          // still numbers the logical line exactly once.
          EditorView.lineWrapping,
          lineNumbers(),
          highlightActiveLine(),
          highlightActiveLineGutter(),
          drawSelection(),
          editorTheme,
          langSlot.current.of([]),
        ],
      }),
    });
    view.current = editor;
    return () => {
      editor.destroy();
      view.current = null;
    };
  }, []);

  // Language support is a dynamic import, so it lands after the first paint.
  useEffect(() => {
    let cancelled = false;
    void loadLanguageExtension(normalizeLanguage(language)).then((extension) => {
      const editor = view.current;
      if (cancelled || !editor) return;
      editor.dispatch({ effects: langSlot.current.reconfigure(extension) });
    });
    return () => {
      cancelled = true;
    };
  }, [language]);

  useEffect(() => {
    const editor = view.current;
    if (!editor || value === doc.current) return;
    doc.current = value;
    const anchor = Math.min(editor.state.selection.main.anchor, value.length);
    editor.dispatch({
      changes: { from: 0, to: editor.state.doc.length, insert: value },
      selection: { anchor },
    });
  }, [rev, value]);

  return <div ref={host} className="h-full min-h-0 [&_.cm-editor]:h-full" />;
}
