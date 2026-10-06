import { useState, type ReactNode } from "react";
import { useAcpRuntime, useAcpSessionId, type AcpMcpServer, type UseAcpRuntimeOptions } from "@assistant-ui/acp";
import { AssistantRuntimeProvider } from "@assistant-ui/react";
import { Thread, type ThreadComponents } from "@/components/assistant-ui/elements/thread.aui";
import { CollapseAwareReasoningGroup } from "@/components/collapse-aware-reasoning";
import { AcpToolCard } from "@/components/tools/acp-tool-card";
import { TooltipProvider } from "@/components/ui/tooltip";
import { useCollapseAllKey } from "@/lib/collapse-all";
import { chatAttachments } from "@/lib/chat-attachments";

const THREAD_COMPONENTS = {
  ToolFallback: AcpToolCard,
  ReasoningGroup: CollapseAwareReasoningGroup,
} satisfies ThreadComponents;

export function ChatThread() {
  const sessionId = useAcpSessionId();
  if (!sessionId) return <p role="status" className="text-muted-foreground p-4 text-sm">Opening chat session…</p>;
  return <Thread components={THREAD_COMPONENTS} />;
}

export function ChatSession({
  url, cwd, mcpServers, protocol, children,
}: {
  url: string;
  cwd: string;
  mcpServers: readonly AcpMcpServer[];
  protocol?: UseAcpRuntimeOptions["protocol"];
  children: (error: string | null) => ReactNode;
}) {
  useCollapseAllKey();
  const [error, setError] = useState<string | null>(null);
  const runtime = useAcpRuntime({
    url, cwd, mcpServers, protocol,
    clientInfo: { name: "crow-chat", version: "0.1.0" },
    restoreOnConnect: true,
    adapters: { attachments: chatAttachments },
    unstable_enableMessageQueue: true,
    onError: (error) => {
      console.error("[acp]", error.message);
      setError(error.message);
    },
  });
  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <TooltipProvider>{children(error)}</TooltipProvider>
    </AssistantRuntimeProvider>
  );
}
