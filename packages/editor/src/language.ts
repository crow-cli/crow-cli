/**
 * Language detection and lazy loading for the editor.
 *
 * Lifted from haklex (`packages/cm-editor/src/language.ts` and
 * `rich-ext-code-snippet/src/utils.ts`): the alias table, the candidate walk
 * and the "try the next candidate if the load throws" loop are all theirs.
 * The extension map is what turns a served path into a language name.
 */
import { LanguageDescription } from "@codemirror/language";
import { languages as languageData } from "@codemirror/language-data";
import type { Extension } from "@codemirror/state";

const EXT_TO_LANG: Record<string, string> = {
  ts: "typescript",
  tsx: "tsx",
  mts: "typescript",
  cts: "typescript",
  js: "javascript",
  jsx: "jsx",
  mjs: "javascript",
  cjs: "javascript",
  py: "python",
  rs: "rust",
  go: "go",
  java: "java",
  html: "html",
  htm: "html",
  css: "css",
  scss: "scss",
  less: "less",
  json: "json",
  jsonc: "json",
  md: "markdown",
  mdx: "markdown",
  sh: "bash",
  bash: "bash",
  zsh: "bash",
  yml: "yaml",
  yaml: "yaml",
  toml: "toml",
  sql: "sql",
  c: "c",
  h: "c",
  cpp: "cpp",
  hpp: "cpp",
  cs: "csharp",
  swift: "swift",
  kt: "kotlin",
  rb: "ruby",
  php: "php",
  vue: "vue",
  svelte: "svelte",
  xml: "xml",
  svg: "xml",
  graphql: "graphql",
  gql: "graphql",
  lua: "lua",
  zig: "zig",
  r: "r",
  dart: "dart",
  ex: "elixir",
  exs: "elixir",
  hs: "haskell",
  ini: "ini",
  conf: "ini",
  diff: "diff",
  patch: "diff",
};

const NAME_TO_LANG: Record<string, string> = {
  dockerfile: "dockerfile",
  makefile: "make",
  justfile: "shell",
  "package.json": "json",
  "cargo.lock": "toml",
};

/** `frontend/src/App.tsx` → `tsx`. Unknown is `text`, never a guess. */
export function languageOfPath(path: string): string {
  const base = path.split("/").pop() ?? path;
  const named = NAME_TO_LANG[base.toLowerCase()];
  if (named) return named;
  const dot = base.lastIndexOf(".");
  if (dot <= 0) return "text";
  return EXT_TO_LANG[base.slice(dot + 1).toLowerCase()] ?? "text";
}

export function normalizeLanguage(language: string | undefined): string {
  if (!language) return "text";
  return language.trim().toLowerCase() || "text";
}

/** What `LanguageDescription.matchLanguageName` also answers to. */
export const languageAliases: Record<string, string[]> = {
  c: ["c"],
  cpp: ["c++", "cpp"],
  cs: ["c#", "csharp"],
  js: ["javascript"],
  jsx: ["javascript jsx", "jsx"],
  md: ["markdown"],
  py: ["python"],
  sh: ["shell", "bash"],
  ts: ["typescript"],
  tsx: ["typescript jsx", "tsx"],
  yml: ["yaml"],
  zsh: ["shell", "bash"],
};

export function getLanguageCandidates(language: string): string[] {
  const normalized = language === "plaintext" ? "text" : language;
  return [normalized, ...(languageAliases[normalized] ?? [])];
}

/**
 * The language support for a name, loaded on demand — `@codemirror/language-data`
 * is a table of dynamic imports, so nothing is fetched until a tab asks.
 */
export async function loadLanguageExtension(language: string): Promise<Extension> {
  if (language === "text") return [];
  for (const candidate of getLanguageCandidates(language)) {
    const matched = LanguageDescription.matchLanguageName(languageData, candidate, true);
    if (!matched) continue;
    try {
      return await matched.load();
    } catch {
      // a broken loader is not a broken editor: try the next candidate
    }
  }
  return [];
}
