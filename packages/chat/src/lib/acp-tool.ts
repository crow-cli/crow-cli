import type {
  AcpToolCallContent,
  AcpToolCallMetadata,
  AcpToolKind,
} from "@assistant-ui/acp";
import type { PartProviderMetadata } from "@assistant-ui/core";

/**
 * Reading a tool call the way crow-cli sends one: the protocol `name` is not
 * emitted yet (PLAN 3.3), the human title carries a `read:`/`edit:` prefix in
 * front of a path, and the interesting payload — a diff, a terminal id, the
 * code a kernel cell ran — lives in the structured content blocks the package
 * keeps on `providerMetadata.acp.content`.
 */

/** The part fields these helpers read; the React props are a superset. */
export type AcpToolPartLike = {
  readonly toolName: string;
  readonly args?: unknown;
  readonly result?: unknown;
  readonly providerMetadata?: PartProviderMetadata | undefined;
};

export const TOOL_KINDS: readonly AcpToolKind[] = [
  "read",
  "edit",
  "delete",
  "move",
  "search",
  "execute",
  "think",
  "fetch",
  "switch_mode",
  "other",
];

const isToolKind = (value: unknown): value is AcpToolKind =>
  typeof value === "string" &&
  (TOOL_KINDS as readonly string[]).includes(value);

export const acpMetadataOf = (
  part: AcpToolPartLike,
): AcpToolCallMetadata | undefined =>
  part.providerMetadata?.acp as AcpToolCallMetadata | undefined;

export const contentBlocksOf = (
  part: AcpToolPartLike,
): readonly AcpToolCallContent[] => acpMetadataOf(part)?.content ?? [];

/**
 * The kind the agent declared. `toolName` is the package's fallback chain
 * (name, then kind, then title), so a `toolName` that IS a kind still tells us
 * the kind when the metadata was never written.
 */
export const toolKindOf = (part: AcpToolPartLike): AcpToolKind => {
  const kind = acpMetadataOf(part)?.kind;
  if (isToolKind(kind)) return kind;
  if (isToolKind(part.toolName)) return part.toolName;
  return "other";
};

const TITLE_PREFIX =
  /^(?:read|write|edit|delete|move|search|fetch|execute)\s*:\s*/i;

/** The title without the `edit: /path` prefix crow-cli hangs off it. */
export const toolTitleOf = (part: AcpToolPartLike): string => {
  const title = acpMetadataOf(part)?.title ?? part.toolName;
  return title.replace(TITLE_PREFIX, "").trim() || title;
};

export type AcpDiffBlock = {
  readonly path?: string;
  readonly patch?: string;
  readonly oldText?: string | null;
  readonly newText?: string;
  readonly isNewFile: boolean;
};

export const diffBlockOf = (part: AcpToolPartLike): AcpDiffBlock | undefined => {
  const block = contentBlocksOf(part).find((block) => block.type === "diff");
  if (!block || block.type !== "diff") return undefined;
  if ("changes" in block) {
    const first = block.changes[0];
    return {
      path: first?.path,
      patch: block.patch?.format === "git_patch" ? block.patch.text : undefined,
      isNewFile: block.changes.length > 0 && block.changes.every((change) => change.operation === "add"),
    };
  }
  return { ...block, isNewFile: block.oldText == null || block.oldText === "" };
};

export const terminalIdOf = (part: AcpToolPartLike): string | undefined => {
  for (const block of contentBlocksOf(part)) {
    if (block.type === "terminal") return block.terminalId;
  }
  return undefined;
};

/** crow-cli sends one block where the spec allows an array; accept both. */
const blocksOf = (content: unknown): readonly Record<string, unknown>[] => {
  const list = Array.isArray(content)
    ? content
    : content && typeof content === "object"
      ? [content]
      : [];
  return list as readonly Record<string, unknown>[];
};

export const textBlocksOf = (part: AcpToolPartLike): readonly string[] => {
  const texts: string[] = [];
  for (const block of contentBlocksOf(part)) {
    if (block.type !== "content") continue;
    for (const inner of blocksOf(block.content)) {
      if (inner.type === "text" && typeof inner.text === "string")
        texts.push(inner.text);
    }
  }
  return texts;
};

const argString = (args: unknown, key: string): string | undefined => {
  if (!args || typeof args !== "object") return undefined;
  const value = (args as Record<string, unknown>)[key];
  return typeof value === "string" && value.length > 0 ? value : undefined;
};

const looksLikePath = (value: string) =>
  value.includes("/") || /^[\w.-]+\.[\w-]+$/.test(value);

const FILE_KINDS: readonly AcpToolKind[] = ["read", "edit", "delete", "move"];

/**
 * The path a file tool acted on: the diff block first — it is the file the
 * agent actually touched — then the arguments, then a title that is nothing
 * but a path once its prefix is stripped.
 */
export const filePathOf = (part: AcpToolPartLike): string | undefined => {
  const path = diffBlockOf(part)?.path;
  if (path) return path;
  for (const key of ["file_path", "path", "notebook_path", "target_file"]) {
    const value = argString(part.args, key);
    if (value) return value;
  }
  // Only a file tool's title is a path — an execute tool's title is the
  // command, and `ls /nope` is not a file called `nope`.
  if (!FILE_KINDS.includes(toolKindOf(part))) return undefined;
  const title = toolTitleOf(part);
  return looksLikePath(title) ? title : undefined;
};

export const fileNameOf = (path: string): string =>
  path.slice(path.lastIndexOf("/") + 1) || path;

export const fileDirOf = (path: string): string => {
  const index = path.lastIndexOf("/");
  return index < 0 ? "" : path.slice(0, index) || "/";
};

const FENCE = /^```[^\n]*\n([\s\S]*?)```$/;

/** CSI / OSC / two-character escapes, then the C0 controls and private-use
 * glyphs left behind. `\n` and `\t` survive; `\r` does not. */
const ANSI =
  /\u001b\[[0-9;?]*[ -/]*[@-~]|\u001b\][^\u0007\u001b]*(?:\u0007|\u001b\\)|\u001b[@-Z\\-_]/g;
const CONTROL = /[\u0000-\u0008\u000b-\u001f\u007f]|\p{Co}/gu;

export type ExecuteDetail = {
  readonly command?: string | undefined;
  readonly code?: string | undefined;
  readonly output?: string | undefined;
  readonly terminalId?: string | undefined;
  readonly exitCode?: number | undefined;
  readonly timedOut?: boolean | undefined;
};

/** crow-cli's v1 `terminal` tool appends the exit code as a prose trailer. */
const EXIT_TRAILER =
  /\n?\[Command (?:completed|failed) with exit code (-?\d+)\]$/;

/**
 * crow-cli's kernel and terminal tools answer with a JSON envelope —
 * `{"exit_code": 0, "output": "...", "raw_bytes_b64": "..."}` — and a terminal
 * card shows the output and a failed exit code, not the envelope's base64
 * shadow of the same bytes. The v1 `terminal` tool has no envelope: it ends
 * with `[Command failed with exit code N]`, which becomes the exit chip.
 */
const unwrapEnvelope = (
  text: string,
): { output?: string; exitCode?: number; timedOut?: boolean } | undefined => {
  const trimmed = text.trim();
  if (!trimmed.startsWith("{")) return undefined;
  try {
    const parsed = JSON.parse(trimmed) as Record<string, unknown>;
    if (typeof parsed.output !== "string") return undefined;
    return {
      output: parsed.output,
      exitCode:
        typeof parsed.exit_code === "number" ? parsed.exit_code : undefined,
      timedOut: parsed.timed_out === true || undefined,
    };
  } catch {
    return undefined;
  }
};

/**
 * A shell tool answers with raw pty bytes: ANSI colour and cursor sequences,
 * the nerd-font glyphs of the user's prompt, carriage returns, and an echo of
 * the command the card already shows on its `$` row. None of it is text a chat
 * thread wants to render.
 */
const cleanPty = (text: string, command?: string) => {
  const cleaned = text
    .replace(ANSI, "")
    .replace(CONTROL, "")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
  const lines = cleaned.split("\n");
  if (command && lines[0]?.trim() === command.trim()) lines.shift();
  return lines.join("\n").trim();
};

/**
 * What an `execute` call ran and what it printed. crow-cli fences the kernel
 * cell's code as the first content block and streams the output after it; the
 * shell path sends no `rawInput` at all — the command IS the title, and a
 * title that is nothing but the tool name is the kernel's.
 */
export const executeDetailOf = (part: AcpToolPartLike): ExecuteDetail => {
  const texts = textBlocksOf(part);
  const fenced = texts.find((text) => FENCE.test(text.trim()));
  const code = fenced ? (fenced.trim().match(FENCE)?.[1] ?? fenced) : undefined;
  const title = toolTitleOf(part);
  const command =
    argString(part.args, "command") ??
    // Only an execute-kind call's title is a command: crow-cli's terminal
    // handler puts the shell line there, the kernel puts its own name.
    (toolKindOf(part) === "execute" && code === undefined && title !== part.toolName
      ? title
      : undefined);
  const printedParts: string[] = [];
  let exitCode: number | undefined;
  let timedOut: boolean | undefined;
  for (const text of texts.filter((t) => t !== fenced)) {
    const envelope = unwrapEnvelope(text);
    if (envelope) {
      if (envelope.output) printedParts.push(envelope.output);
      exitCode = envelope.exitCode ?? exitCode;
      timedOut = envelope.timedOut ?? timedOut;
      continue;
    }
    const trailer = text.match(EXIT_TRAILER);
    if (trailer) exitCode = Number(trailer[1]);
    printedParts.push(
      cleanPty(trailer ? text.replace(EXIT_TRAILER, "") : text, command),
    );
  }
  const printed = printedParts.join("\n").trim();
  const output =
    printed ||
    (fenced === undefined && typeof part.result === "string"
      ? cleanPty(part.result, command)
      : "");
  return {
    command,
    code: code?.trim() || undefined,
    output: output || undefined,
    terminalId: terminalIdOf(part),
    exitCode,
    timedOut,
  };
};
