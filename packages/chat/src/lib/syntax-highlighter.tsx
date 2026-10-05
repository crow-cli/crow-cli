"use client";

import type { FC } from "react";
import { PrismAsyncLight } from "react-syntax-highlighter";
import type { SyntaxHighlighterProps } from "@assistant-ui/react-markdown";
import bash from "react-syntax-highlighter/dist/esm/languages/prism/bash";
import diff from "react-syntax-highlighter/dist/esm/languages/prism/diff";
import json from "react-syntax-highlighter/dist/esm/languages/prism/json";
import jsx from "react-syntax-highlighter/dist/esm/languages/prism/jsx";
import python from "react-syntax-highlighter/dist/esm/languages/prism/python";
import sql from "react-syntax-highlighter/dist/esm/languages/prism/sql";
import toml from "react-syntax-highlighter/dist/esm/languages/prism/toml";
import tsx from "react-syntax-highlighter/dist/esm/languages/prism/tsx";
import typescript from "react-syntax-highlighter/dist/esm/languages/prism/typescript";
import yaml from "react-syntax-highlighter/dist/esm/languages/prism/yaml";

import { cn } from "@/lib/utils";

PrismAsyncLight.registerLanguage("python", python);
PrismAsyncLight.registerLanguage("bash", bash);
PrismAsyncLight.registerLanguage("sh", bash);
PrismAsyncLight.registerLanguage("shell", bash);
PrismAsyncLight.registerLanguage("json", json);
PrismAsyncLight.registerLanguage("typescript", typescript);
PrismAsyncLight.registerLanguage("ts", typescript);
PrismAsyncLight.registerLanguage("tsx", tsx);
PrismAsyncLight.registerLanguage("jsx", jsx);
PrismAsyncLight.registerLanguage("yaml", yaml);
PrismAsyncLight.registerLanguage("diff", diff);
PrismAsyncLight.registerLanguage("toml", toml);
PrismAsyncLight.registerLanguage("sql", sql);

// Token colours ride the theme's CSS variables, so light/dark/macchiato
// each get their own palette without a second highlighter tree.
const token = (color: string, extra?: Record<string, string>) => ({
  color,
  ...extra,
});

const CODE_THEME: Record<string, Record<string, string>> = {
  comment: token("var(--code-comment)", { fontStyle: "italic" }),
  prolog: token("var(--code-comment)"),
  doctype: token("var(--code-comment)"),
  cdata: token("var(--code-comment)"),
  punctuation: token("var(--code-punctuation)"),
  property: token("var(--code-property)"),
  tag: token("var(--code-type)"),
  symbol: token("var(--code-type)"),
  string: token("var(--code-string)"),
  char: token("var(--code-string)"),
  "attr-value": token("var(--code-string)"),
  regex: token("var(--code-string)"),
  boolean: token("var(--code-number)"),
  number: token("var(--code-number)"),
  constant: token("var(--code-number)"),
  operator: token("var(--code-operator)"),
  entity: token("var(--code-operator)"),
  url: token("var(--code-operator)"),
  function: token("var(--code-function)"),
  builtin: token("var(--code-function)"),
  "class-name": token("var(--code-type)"),
  classname: token("var(--code-type)"),
  "attr-name": token("var(--code-attr)"),
  variable: token("var(--code-property)"),
  keyword: token("var(--code-keyword)"),
  inserted: token("var(--code-inserted)"),
  deleted: token("var(--code-deleted)"),
};

/** The markdown code-fence slot: renders inside the app's Pre/Code. */
export const CodeHighlighter: FC<SyntaxHighlighterProps> = ({
  components: { Pre, Code },
  language,
  code,
}) => (
  <PrismAsyncLight
    PreTag={Pre}
    CodeTag={Code}
    style={CODE_THEME}
    customStyle={{ background: "transparent", margin: 0, padding: 0 }}
    useInlineStyles
    language={language}
  >
    {code}
  </PrismAsyncLight>
);

const ToolPre: FC<React.ComponentProps<"pre">> = ({ className, ...props }) => (
  <pre
    className={cn(
      "text-foreground/90 overflow-x-auto px-3 py-2 whitespace-pre",
      className,
    )}
    {...props}
  />
);

const ToolCode: FC<React.ComponentProps<"code">> = (props) => (
  <code {...props} />
);

/**
 * Highlighted source inside a tool card (an `execute` cell, a fetched
 * snippet): same tokens as the markdown fences, terminal styling.
 */
export const ToolCodeBlock: FC<{
  code: string;
  language?: string;
  className?: string;
  "data-slot"?: string;
}> = ({ code, language = "python", className, ...rest }) => (
  <div className={className} {...rest}>
    <CodeHighlighter
      components={{ Pre: ToolPre, Code: ToolCode }}
      language={language}
      code={code}
    />
  </div>
);
