import type { ReactNode } from "react";
import { BrainIcon } from "lucide-react";
import {
  ReasoningGroupDisclosure,
  useReasoningFirstLine,
} from "@/components/assistant-ui/elements/reasoning.aui";
import type { ThreadGroupPart } from "@/components/assistant-ui/elements/thread.aui";
import { useCollapseAll } from "@/lib/collapse-all";

const NO_INDICES: readonly number[] = [];

/**
 * The default reasoning group, except that collapse-all trades the disclosure
 * for the TUI's one-line thought: brain glyph plus the first line of the
 * first reasoning part, truncated by the row.
 */
export function CollapseAwareReasoningGroup({
  group,
  children,
}: {
  group: ThreadGroupPart;
  children?: ReactNode;
}) {
  const collapsed = useCollapseAll();
  const firstLine = useReasoningFirstLine(collapsed ? group.indices : NO_INDICES);

  if (collapsed) {
    return (
      <div
        data-testid="thought-collapsed"
        className="text-muted-foreground flex min-w-0 items-center gap-2 py-0.5 text-xs"
      >
        <BrainIcon className="size-3.5 shrink-0" aria-hidden />
        <span className="truncate">{firstLine ?? "thought"}</span>
      </div>
    );
  }

  return (
    <ReasoningGroupDisclosure
      indices={group.indices}
      running={group.status.type === "running"}
    >
      {children}
    </ReasoningGroupDisclosure>
  );
}
