import { useCallback, useMemo, useState } from "react";
import {
  Thread,
  type ThreadComponents,
} from "@/components/assistant-ui/elements/thread.aui";
import { CollapseAwareReasoningGroup } from "@/components/collapse-aware-reasoning";
import { AcpToolCard } from "@/components/tools/acp-tool-card";
import { AppHeader } from "@/components/app-header";
import { AppSidebar } from "@/components/app-sidebar";
import { WorkSplit } from "@/components/work/work-split";
import { TooltipProvider } from "@/components/ui/tooltip";
import { useAcpRuntime } from "@assistant-ui/acp";
import { AssistantRuntimeProvider } from "@assistant-ui/react";
import { useCollapseAllKey } from "@/lib/collapse-all";
import { parseMcpConfig } from "@/lib/mcp-config";
import {
  DEFAULT_CWD,
  useAcpUrlSetting,
  useCwdSetting,
  useMcpSetting,
} from "@/lib/settings";
import { useTheme, type Theme } from "@/lib/theme";
import { useWorkStore } from "@/lib/work-store";

// Tool calls render through the ACP card: kind icon, path link, diff,
// terminal — see components/tools/acp-tool-card.tsx.
const THREAD_COMPONENTS = {
  ToolFallback: AcpToolCard,
  ReasoningGroup: CollapseAwareReasoningGroup,
} satisfies ThreadComponents;

// The runtime owns its session, and both cwd and the MCP tool supply are
// read at session/new, so any change to either rebuilds the whole subtree.
function Chat({
  acpUrl,
  onSaveAcpUrl,
  cwd,
  mcpText,
  onSaveCwd,
  onSaveMcp,
  theme,
  onTheme,
}: {
  acpUrl: string;
  onSaveAcpUrl: (next: string) => void;
  cwd: string;
  mcpText: string;
  onSaveCwd: (next: string) => void;
  onSaveMcp: (next: string) => void;
  theme: Theme;
  onTheme: (next: Theme) => void;
}) {
  useCollapseAllKey();
  const [acpError, setAcpError] = useState<string | null>(null);
  const mcpServers = useMemo(() => parseMcpConfig(mcpText).servers, [mcpText]);
  const runtime = useAcpRuntime({
    url: acpUrl,
    cwd,
    mcpServers,
    clientInfo: { name: "crow-chat", version: "0.1.0" },
    // The session exists before the first prompt: reload lands on the
    // agent's newest thread, an empty directory mints one, and the header
    // shows its id while the composer is still empty.
    restoreOnConnect: true,
    // A send made mid-turn queues behind it and goes out as its own
    // `session/prompt` when it settles; ctrl+enter steers instead, putting the
    // prompt on the wire at once — see components/send-queue.tsx for the shelf
    // that shows what is waiting.
    unstable_enableMessageQueue: true,
    onError: (error) => {
      console.error("[acp]", error.message);
      setAcpError(error.message);
    },
  });
  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <TooltipProvider>
        <div className="flex h-full">
          <AppSidebar />
          <main className="flex min-w-0 flex-1 flex-col">
            <AppHeader
              acpError={acpError}
              acpUrl={acpUrl}
              onSaveAcpUrl={onSaveAcpUrl}
              cwd={cwd}
              onSaveCwd={onSaveCwd}
              mcpText={mcpText}
              onSaveMcp={onSaveMcp}
              theme={theme}
              onTheme={onTheme}
            />
            <WorkSplit>
              <div className="h-full min-h-0">
                <Thread components={THREAD_COMPONENTS} />
              </div>
            </WorkSplit>
          </main>
        </div>
      </TooltipProvider>
    </AssistantRuntimeProvider>
  );
}

export default function App() {
  const [acpUrl, setAcpUrl] = useAcpUrlSetting();
  const [cwd, setCwd] = useCwdSetting();
  const [mcpText, setMcpText] = useMcpSetting();
  const [theme, setTheme] = useTheme();

  // Saving the cwd moves both the chat session (the `key` below rebuilds the
  // runtime) and the work pane's served root — the same directory, two
  // consumers, one choice.
  const saveCwd = useCallback(
    (next: string) => {
      const value = next.trim() || DEFAULT_CWD;
      setCwd(next);
      void useWorkStore.getState().reroot(value);
    },
    [setCwd],
  );

  return (
    <Chat
      key={`${acpUrl}\n${cwd}\n${mcpText}`}
      acpUrl={acpUrl}
      onSaveAcpUrl={setAcpUrl}
      cwd={cwd}
      mcpText={mcpText}
      onSaveCwd={saveCwd}
      onSaveMcp={setMcpText}
      theme={theme}
      onTheme={setTheme}
    />
  );
}
