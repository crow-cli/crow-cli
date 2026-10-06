"use client";

import { memo, useState, type ElementType, type ReactNode } from "react";
import {
  AlertCircleIcon,
  BracesIcon,
  BrainIcon,
  CheckIcon,
  ChevronDownIcon,
  CopyIcon,
  FilePenIcon,
  FileTextIcon,
  FolderInputIcon,
  GlobeIcon,
  LoaderIcon,
  SearchIcon,
  SlidersHorizontalIcon,
  SquareTerminalIcon,
  Trash2Icon,
  WrenchIcon,
  XCircleIcon,
} from "lucide-react";
import type { AcpToolKind } from "@assistant-ui/acp";
import {
  useToolCallElapsed,
  type ToolCallMessagePartComponent,
  type ToolCallMessagePartProps,
  type ToolCallMessagePartStatus,
} from "@assistant-ui/react";
import {
  offersInterruptAction,
  ToolFallbackApproval,
  ToolFallbackArgs,
  ToolFallbackError,
  ToolFallbackResult,
  ToolFallbackRoot,
} from "@/components/assistant-ui/elements/tool-fallback.aui";
import { DiffViewer } from "@/components/ui/diff-viewer";
import { CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { useCopyToClipboard } from "@/hooks/use-copy-to-clipboard";
import { useCollapseAll } from "@/lib/collapse-all";
import { ToolCodeBlock } from "@/lib/syntax-highlighter";
import { cn } from "@/lib/utils";
import {
  acpMetadataOf,
  diffBlockOf,
  executeDetailOf,
  fileNameOf,
  fileDirOf,
  filePathOf,
  toolKindOf,
  toolTitleOf,
  type AcpToolPartLike,
  type ExecuteDetail,
} from "@/lib/acp-tool";

/**
 * crow-cli's tool calls, drawn the way the agent means them: a diff for an
 * edit, an all-green view for a write, a path link with no body dump for a
 * read, a terminal card for a shell or kernel cell, and a generic card with
 * collapsible args/result for everything else.
 */

const KIND_ICON: Record<AcpToolKind, ElementType> = {
  read: FileTextIcon,
  edit: FilePenIcon,
  delete: Trash2Icon,
  move: FolderInputIcon,
  search: SearchIcon,
  execute: SquareTerminalIcon,
  think: BrainIcon,
  fetch: GlobeIcon,
  switch_mode: SlidersHorizontalIcon,
  other: WrenchIcon,
};

const VERB: Record<AcpToolKind, string> = {
  read: "read",
  edit: "edited",
  delete: "deleted",
  move: "moved",
  search: "searched",
  execute: "ran",
  think: "thought",
  fetch: "fetched",
  switch_mode: "switched mode",
  other: "used",
};

type Pill = {
  label: string;
  Icon: ElementType;
  className: string;
  spin?: boolean;
};

const statusPill = (
  status: ToolCallMessagePartStatus | undefined,
  isError: boolean | undefined,
): Pill => {
  if (status?.type === "running")
    return {
      label: "Running",
      Icon: LoaderIcon,
      className: "text-muted-foreground border-border",
      spin: true,
    };
  if (status?.type === "requires-action")
    return {
      label: "Waiting",
      Icon: AlertCircleIcon,
      className: "text-warning border-warning/30 bg-warning/10",
    };
  if (status?.type === "incomplete" || isError) {
    const cancelled =
      status?.type === "incomplete" && status.reason === "cancelled";
    return {
      label: cancelled ? "Cancelled" : "Failed",
      Icon: XCircleIcon,
      className: cancelled
        ? "text-muted-foreground border-border"
        : "text-destructive border-destructive/30 bg-destructive/10",
    };
  }
  return {
    label: "Done",
    Icon: CheckIcon,
    className: "text-success border-success/30 bg-success/10",
  };
};

const formatElapsed = (ms: number) => {
  if (ms < 1000) return "<1s";
  const seconds = ms / 1000;
  if (seconds < 60) return `${(Math.floor(seconds * 10) / 10).toFixed(1)}s`;
  return `${Math.floor(seconds / 60)}m ${Math.floor(seconds % 60)}s`;
};

function Elapsed() {
  const elapsedMs = useToolCallElapsed();
  if (elapsedMs === undefined) return null;
  return (
    <span
      data-slot="acp-tool-elapsed"
      className="text-muted-foreground text-xs tabular-nums"
    >
      {formatElapsed(elapsedMs)}
    </span>
  );
}

/** A path is the one thing worth clicking: copy it, since the browser has no
 * editor to open it in. */
function PathLink({ path }: { path: string }) {
  const { isCopied, copyToClipboard } = useCopyToClipboard({
    copiedDuration: 1500,
  });
  const dir = fileDirOf(path);
  return (
    <button
      type="button"
      data-slot="acp-tool-path"
      title={`${path} — copy path`}
      aria-label={`Copy path ${path}`}
      onClick={() => copyToClipboard(path)}
      className="group/path text-muted-foreground hover:text-foreground flex min-w-0 max-w-full items-center gap-1 rounded text-sm transition-colors"
    >
      {dir && (
        <span className="truncate text-xs opacity-70">{dir}/</span>
      )}
      <span className="text-foreground truncate font-medium">
        {fileNameOf(path)}
      </span>
      {isCopied ? (
        <CheckIcon data-slot="acp-tool-path-copied" className="text-success size-3 shrink-0" />
      ) : (
        <CopyIcon className="size-3 shrink-0 opacity-0 transition-opacity group-hover/path:opacity-70" />
      )}
    </button>
  );
}

/** The diff viewer's colors come from its own CSS variables; point them at
 * this app's semantic tokens so a theme change recolors the diff too. */
const DIFF_TOKENS = cn(
  "[--diff-add-bg:color-mix(in_oklab,var(--success)_12%,transparent)]",
  "[--diff-add-rule:var(--success)]",
  "[--diff-add-text:var(--success)]",
  "[--diff-add-text-dark:var(--success)]",
  "[--diff-del-bg:color-mix(in_oklab,var(--destructive)_12%,transparent)]",
  "[--diff-del-rule:var(--destructive)]",
  "[--diff-del-text:var(--destructive)]",
  "[--diff-del-text-dark:var(--destructive)]",
);

function DiffBody({ part, path }: { part: AcpToolPartLike; path?: string }) {
  const diff = diffBlockOf(part);
  if (!diff) return null;
  const name = path ?? diff.path;
  return (
    <div data-slot="acp-tool-diff" data-new-file={diff.isNewFile}>
      <DiffViewer
        patch={diff.patch}
        oldFile={diff.newText !== undefined ? { content: diff.oldText ?? "", name } : undefined}
        newFile={diff.newText !== undefined ? { content: diff.newText, name } : undefined}
        viewMode="unified"
        maxCollapsedLines={16}
        className={cn("rounded-md", DIFF_TOKENS)}
      />
    </div>
  );
}

function TerminalBody({ detail }: { detail: ExecuteDetail }) {
  const { command, code, output, terminalId, exitCode, timedOut } = detail;
  if (!command && !code && !output && !terminalId && exitCode === undefined)
    return null;
  const failed = timedOut || (exitCode !== undefined && exitCode !== 0);
  return (
    <div
      data-slot="acp-tool-terminal"
      className="bg-muted/40 border-foreground/10 overflow-hidden rounded-md border font-mono text-xs"
    >
      {command && (
        <div
          data-slot="acp-tool-terminal-command"
          className="flex gap-2 px-3 py-2"
        >
          <span className="text-muted-foreground select-none">$</span>
          <span className="break-all whitespace-pre-wrap">{command}</span>
        </div>
      )}
      {code && (
        <ToolCodeBlock
          data-slot="acp-tool-terminal-code"
          code={code}
          language="python"
          className={cn(command && "border-foreground/10 border-t")}
        />
      )}
      {output && (
        <pre
          data-slot="acp-tool-terminal-output"
          className={cn(
            "text-muted-foreground max-h-72 overflow-auto px-3 py-2 whitespace-pre-wrap",
            (command || code) && "border-foreground/10 border-t",
          )}
        >
          {output}
        </pre>
      )}
      {failed && (
        <div
          data-slot="acp-tool-terminal-exit"
          className={cn(
            "border-foreground/10 border-t px-3 py-1 text-[10px] font-medium",
            timedOut ? "text-warning" : "text-destructive",
          )}
        >
          {timedOut ? "timed out" : `exit ${exitCode}`}
        </div>
      )}
      {terminalId && (
        <div
          data-slot="acp-tool-terminal-id"
          className="text-muted-foreground/70 border-foreground/10 border-t px-3 py-1 text-[10px]"
        >
          terminal {terminalId}
        </div>
      )}
    </div>
  );
}

function CardContent({ children }: { children: ReactNode }) {
  return (
    <CollapsibleContent
      data-slot="acp-tool-content"
      className={cn(
        "relative overflow-hidden text-sm outline-none",
        "group/collapsible-content ease-[cubic-bezier(0.32,0.72,0,1)] motion-reduce:animate-none",
        "data-closed:animate-collapsible-up data-open:animate-collapsible-down",
        "data-closed:fill-mode-forwards data-closed:pointer-events-none",
        "[--tw-duration:var(--animation-duration)]",
      )}
    >
      <div
        className={cn(
          "flex flex-col gap-2 px-1 pt-2 pb-1 ease-[cubic-bezier(0.32,0.72,0,1)] motion-reduce:animate-none",
          "group-data-open/collapsible-content:animate-in group-data-open/collapsible-content:fade-in-0 group-data-open/collapsible-content:slide-in-from-top-1",
          "group-data-closed/collapsible-content:animate-out group-data-closed/collapsible-content:fade-out-0 group-data-closed/collapsible-content:slide-out-to-top-1",
          "group-data-closed/collapsible-content:animation-duration-(--animation-duration) group-data-open/collapsible-content:animation-duration-(--animation-duration)",
        )}
      >
        {children}
      </div>
    </CollapsibleContent>
  );
}

const safeParse = (text: string | undefined) => {
  if (!text) return undefined;
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
};

/** The TUI's `┌─ json ┐`: everything the wire carried, unrendered. */
function RawBody({
  part,
  kind,
  title,
}: {
  part: ToolCallMessagePartProps;
  kind: AcpToolKind;
  title: string;
}) {
  const meta = acpMetadataOf(part);
  const payload = {
    kind,
    title,
    name: meta?.name,
    status: part.status,
    args: part.args ?? safeParse(part.argsText),
    result: part.result,
    content: meta?.content,
  };
  return (
    <pre
      data-slot="acp-tool-raw"
      className="bg-muted/40 border-foreground/10 max-h-96 overflow-auto rounded-md border p-2 font-mono text-[11px] select-text whitespace-pre-wrap"
    >
      {JSON.stringify(payload, null, 2)}
    </pre>
  );
}

const isSettledApproval = (approval: ToolCallMessagePartProps["approval"]) =>
  approval != null &&
  (approval.approved !== undefined || approval.resolution !== undefined);

const AcpToolCardImpl: ToolCallMessagePartComponent = (props) => {
  const { argsText, result, status, isError, addResult, resume, interrupt, approval, respondToApproval } =
    props;
  const kind = toolKindOf(props);
  const path = filePathOf(props);
  const diff = diffBlockOf(props);
  const Icon = KIND_ICON[kind] ?? WrenchIcon;

  const isRequiresAction = status?.type === "requires-action";
  const showApproval =
    (isRequiresAction && offersInterruptAction(status, approval, interrupt)) ||
    isSettledApproval(approval);

  const newFile = diff?.isNewFile ?? false;
  const detail = kind === "execute" ? executeDetailOf(props) : undefined;
  // The programmatic name the agent reports (PLAN 3.3): worth showing when it
  // says more than the kind — `write` vs `edit`, `terminal` vs a kernel cell.
  const toolName = acpMetadataOf(props)?.name;

  let body: ReactNode = null;
  let collapsible = true;
  let defaultOpen = isRequiresAction;
  if (diff) {
    body = <DiffBody part={props} path={path} />;
    defaultOpen = true;
  } else if (detail) {
    body = <TerminalBody detail={detail} />;
    defaultOpen = true;
  } else if (kind === "read") {
    // A read is the file it touched; dumping the body back into the thread
    // is noise the agent already has.
    collapsible = false;
  } else {
    body = (
      <>
        <ToolFallbackArgs argsText={argsText} />
        <ToolFallbackResult result={result} />
      </>
    );
  }

  const [open, setOpen] = useState(defaultOpen || !collapsible);
  const [peek, setPeek] = useState(false);
  const [raw, setRaw] = useState(false);
  const collapsedAll = useCollapseAll();
  const pill = statusPill(status, isError);
  const verb = kind === "edit" && newFile ? "wrote" : VERB[kind];
  const title = toolTitleOf(props);

  // collapse-all: one line carrying the kind glyph, the label and the raw
  // args, exactly like the TUI's `⏺ execute  {"code":…`. Clicking peeks at
  // this one call without expanding the rest; closing it returns to the line.
  if (collapsedAll && !peek) {
    const label = path ? `${verb} ${fileNameOf(path)}` : title;
    const args = (argsText ?? "").replace(/\s+/g, " ").trim();
    return (
      <button
        type="button"
        data-testid="acp-tool-collapsed"
        data-kind={kind}
        title="Expand this call"
        onClick={() => {
          setPeek(true);
          setOpen(true);
        }}
        className="text-muted-foreground hover:text-foreground flex w-full min-w-0 items-center gap-2 rounded py-0.5 ps-1 text-start text-xs transition-colors"
      >
        <Icon className="size-3.5 shrink-0" aria-hidden />
        <span
          className={cn(
            "shrink-0",
            kind === "execute" && "font-mono text-[11px]",
          )}
        >
          {label}
        </span>
        {args && (
          <span className="truncate font-mono text-[11px] opacity-70">
            {args}
          </span>
        )}
        <span
          className={cn(
            "ml-auto shrink-0 rounded-full border px-1.5 py-px text-[10px] leading-tight font-medium",
            pill.className,
          )}
        >
          {pill.label}
        </span>
      </button>
    );
  }

  const heading = (
    <>
      <Icon
        data-slot="acp-tool-icon"
        data-kind={kind}
        className="text-muted-foreground size-4 shrink-0"
        aria-hidden
      />
      {path ? (
        <>
          <span
            data-slot="acp-tool-verb"
            className="text-muted-foreground shrink-0 text-xs"
          >
            {verb}
          </span>
          <PathLink path={path} />
        </>
      ) : (
        <span
          data-slot="acp-tool-title"
          className={cn(
            "text-foreground min-w-0 flex-1 truncate text-sm",
            kind === "execute" && "font-mono text-xs",
          )}
        >
          {title}
        </span>
      )}
      {toolName && toolName !== kind && (
        <span
          data-slot="acp-tool-name"
          className="text-muted-foreground/80 border-foreground/10 shrink-0 rounded border px-1 py-px font-mono text-[10px] leading-tight"
        >
          {toolName}
        </span>
      )}
      {newFile && (
        <span
          data-slot="acp-tool-new-file"
          className="text-success border-success/30 bg-success/10 shrink-0 rounded-full border px-1.5 py-px text-[10px] leading-tight"
        >
          new file
        </span>
      )}
      <span
        data-slot="acp-tool-status"
        data-status={pill.label.toLowerCase()}
        className={cn(
          "flex shrink-0 items-center gap-1 rounded-full border px-1.5 py-px text-[10px] leading-tight font-medium",
          pill.className,
        )}
      >
        <pill.Icon className={cn("size-2.5", pill.spin && "animate-spin [animation-duration:0.6s]")} aria-hidden />
        {pill.label}
      </span>
      <Elapsed />
      {collapsible && (
        <ChevronDownIcon
          data-slot="acp-tool-chevron"
          className={cn(
            "text-muted-foreground size-4 shrink-0 transition-transform duration-(--animation-duration) ease-[cubic-bezier(0.32,0.72,0,1)] motion-reduce:transition-none",
            "-rotate-90 group-data-open/trigger:rotate-0",
          )}
          aria-hidden
        />
      )}
    </>
  );

  const headerClass =
    "text-muted-foreground hover:text-foreground flex w-full min-w-0 items-center gap-2 rounded py-1.5 pe-1 ps-1 text-start transition-[color,scale] active:scale-[0.99]";

  const approvalBlock = showApproval ? (
    <ToolFallbackApproval
      addResult={addResult}
      resume={resume}
      interrupt={interrupt}
      approval={approval}
      respondToApproval={respondToApproval}
      status={status}
    />
  ) : null;

  return (
    <ToolFallbackRoot
      open={open}
      onOpenChange={
        collapsible
          ? (next) => {
              setOpen(next);
              if (!next && collapsedAll) setPeek(false);
            }
          : undefined
      }
      className="aui-acp-tool-root py-0.5"
      data-slot="acp-tool-root"
      data-kind={kind}
    >
      <div className="flex w-full min-w-0 items-start gap-1">
        {collapsible ? (
          <CollapsibleTrigger
            data-slot="acp-tool-trigger"
            className={cn(headerClass, "group/trigger min-w-0 flex-1")}
          >
            {heading}
          </CollapsibleTrigger>
        ) : (
          <div
            data-slot="acp-tool-header"
            className={cn(
              headerClass,
              "hover:text-muted-foreground min-w-0 flex-1 cursor-default active:scale-100",
            )}
          >
            {heading}
          </div>
        )}
        <button
          type="button"
          data-testid="acp-tool-raw"
          data-state={raw ? "on" : "off"}
          aria-label={raw ? "Show rendered result" : "Show raw JSON"}
          title={raw ? "Rendered" : "Raw JSON"}
          onClick={() => setRaw((v) => !v)}
          className={cn(
            "text-muted-foreground hover:text-foreground mt-1.5 me-1 shrink-0 rounded p-0.5 transition-colors",
            raw && "bg-muted text-foreground",
          )}
        >
          <BracesIcon className="size-3.5" aria-hidden />
        </button>
      </div>
      {raw || collapsible ? (
        <CardContent>
          {raw ? (
            <RawBody part={props} kind={kind} title={title} />
          ) : (
            <>
              {body}
              {approvalBlock}
              <ToolFallbackError status={status} />
            </>
          )}
        </CardContent>
      ) : (
        (approvalBlock || status?.type === "incomplete") && (
          <div className="flex flex-col gap-2 px-1 pb-1">
            {approvalBlock}
            <ToolFallbackError status={status} />
          </div>
        )
      )}
    </ToolFallbackRoot>
  );
};

export const AcpToolCard = memo(AcpToolCardImpl) as ToolCallMessagePartComponent;
AcpToolCard.displayName = "AcpToolCard";
