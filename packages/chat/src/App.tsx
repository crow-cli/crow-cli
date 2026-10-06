import { useCallback, useMemo } from "react";
import { ChatSession, ChatThread } from "@/components/chat-session";
import { AppHeader } from "@/components/app-header";
import { AppSidebar } from "@/components/app-sidebar";
import { WorkSplit } from "@/components/work/work-split";
import { parseMcpConfig } from "@/lib/mcp-config";
import {
  DEFAULT_CWD,
  useAcpUrlSetting,
  useCwdSetting,
  useMcpSetting,
} from "@/lib/settings";
import { useTheme, type Theme } from "@/lib/theme";
import { useWorkStore } from "@/lib/work-store";

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
  const mcpServers = useMemo(() => parseMcpConfig(mcpText).servers, [mcpText]);
  return (
    <ChatSession url={acpUrl} cwd={cwd} mcpServers={mcpServers}>
      {(acpError) => (
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
              <div className="h-full min-h-0"><ChatThread /></div>
            </WorkSplit>
          </main>
        </div>
      )}
    </ChatSession>
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
