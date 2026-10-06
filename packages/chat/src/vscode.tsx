import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { SettingsIcon, ChevronsDownUpIcon } from "lucide-react";
import { useAcpConnectionState } from "@assistant-ui/acp";
import { ChatSession, ChatThread } from "@/components/chat-session";
import { ChatAccessibility } from "@/components/vscode-accessibility";
import { AppSidebar } from "@/components/app-sidebar";
import { ModelSelector } from "@/components/model-selector";
import { SessionBadge } from "@/components/session-badge";
import { ContextMeter } from "@/components/context-meter";
import { Button } from "@/components/ui/button";
import { collapseAll } from "@/lib/collapse-all";
import { parseMcpConfig } from "@/lib/mcp-config";
import "./index.css";
import "./vscode.css";

declare function acquireVsCodeApi(): { postMessage(message: unknown): void };
const vscode = acquireVsCodeApi();
const settings = JSON.parse(document.getElementById("crow-acp-settings")!.textContent!) as {
  host: "editor" | "sidebar";
  endpoint: string;
  cwd: string;
  protocol: "auto" | "1" | "2";
  mcpConfig: string;
  accessibilityVerbosity: boolean;
};
const mcp = parseMcpConfig(settings.mcpConfig);

function Header({ error }: { error: string | null }) {
  const state = useAcpConnectionState();
  return (
    <header className="flex flex-wrap items-center gap-2 border-b px-3 py-2">
      <span role="status" aria-live="polite" className="text-muted-foreground text-xs" title={settings.endpoint}>{state}</span>
      <SessionBadge className="min-w-0 flex-1" />
      <ModelSelector />
      <ContextMeter />
      <ChatAccessibility verbosity={settings.accessibilityVerbosity} />
      <Button variant="ghost" size="icon" aria-label="Toggle all tool calls and thoughts" title="Toggle all · Ctrl+Shift+O" onClick={() => collapseAll.toggle()}><ChevronsDownUpIcon className="size-4" /></Button>
      <Button variant="ghost" size="icon" aria-label="ACP settings" title="ACP settings" onClick={() => vscode.postMessage({ type: "settings" })}><SettingsIcon className="size-4" /></Button>
      {error && <p role="alert" className="text-destructive w-full text-xs">{error}</p>}
    </header>
  );
}

function App() {
  const [dark, setDark] = useState(() => !document.body.classList.contains("vscode-light") && !document.body.classList.contains("vscode-high-contrast-light"));
  useEffect(() => {
    const observer = new MutationObserver(() => setDark(!document.body.classList.contains("vscode-light") && !document.body.classList.contains("vscode-high-contrast-light")));
    observer.observe(document.body, { attributes: true, attributeFilter: ["class"] });
    return () => observer.disconnect();
  }, []);
  if (mcp.error) return <p role="alert">Invalid MCP configuration: {mcp.error}</p>;
  return (
    <div className={`${dark ? "dark" : ""} h-full`}>
      <ChatSession url={settings.endpoint} cwd={settings.cwd} mcpServers={mcp.servers} protocol={settings.protocol === "auto" ? "auto" : Number(settings.protocol) as 1 | 2}>
        {(error) => (
          <div data-host={settings.host} className="crow-chat-layout flex h-full">
            <AppSidebar defaultCollapsed={settings.host === "sidebar"} />
            <main aria-label="Crow ACP Chat" className="flex min-h-0 min-w-0 flex-1 flex-col">
              <Header error={error} />
              <div className="min-h-0 flex-1"><ChatThread /></div>
            </main>
          </div>
        )}
      </ChatSession>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<StrictMode><App /></StrictMode>);
