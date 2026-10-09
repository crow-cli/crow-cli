import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { SettingsIcon, ChevronsDownUpIcon, HistoryIcon } from "lucide-react";
import { useAcpAgentCapabilities, useAcpConnectionState, useAcpSessionId } from "@assistant-ui/acp";
import { useAui, useAuiState } from "@assistant-ui/react";
import { ChatSession, ChatThread } from "@/components/chat-session";
import { ChatAccessibility } from "@/components/vscode-accessibility";
import { ModelSelector } from "@/components/model-selector";
import { SessionBadge } from "@/components/session-badge";
import { ContextGauge } from "@/components/context-meter";
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

/**
 * Session list, model and context live elsewhere now: the view title carries
 * new-session, the session dropdown, collapse-all and settings, so the header
 * keeps only what is about *this* chat. An editor-tab webview has no view title
 * of its own, so it keeps the three buttons the sidebar gets from VS Code's
 * menus — the session one asks the extension to open the same dropdown.
 */
function Header({ error }: { error: string | null }) {
  const state = useAcpConnectionState();
  return (
    <header className="flex flex-wrap items-center gap-2 border-b px-3 py-2">
      <span role="status" aria-live="polite" className="text-muted-foreground text-xs" title={settings.endpoint}>{state}</span>
      <SessionBadge className="min-w-0 flex-1" />
      <ChatAccessibility verbosity={settings.accessibilityVerbosity} />
      {settings.host === "editor" && <>
        <Button variant="ghost" size="icon" aria-label="Switch session" title="Switch session" onClick={() => vscode.postMessage({ type: "pick-session" })}><HistoryIcon className="size-4" /></Button>
        <Button variant="ghost" size="icon" aria-label="Toggle all tool calls and thoughts" title="Toggle all · Ctrl+Shift+O" onClick={() => collapseAll.toggle()}><ChevronsDownUpIcon className="size-4" /></Button>
        <Button variant="ghost" size="icon" aria-label="ACP settings" title="ACP settings" onClick={() => vscode.postMessage({ type: "settings" })}><SettingsIcon className="size-4" /></Button>
      </>}
      {error && <p role="alert" className="text-destructive w-full text-xs">{error}</p>}
    </header>
  );
}

/** Model and context sit under the composer, out of the thread's way. */
function Footer() {
  return (
    <footer className="flex items-center justify-between gap-2 border-t px-2 py-1">
      <ModelSelector />
      <ContextGauge />
    </footer>
  );
}

/**
 * The native half of the sidebar. The extension cannot ask the agent anything
 * itself, so this publishes the runtime's thread list over postMessage and
 * answers the extension's open/new/delete/refresh messages with store calls —
 * the same adapter the in-webview list used to drive.
 */
function VscodeBridge() {
  const aui = useAui();
  const threads = useAuiState((s) => s.threads.threadItems);
  const activeId = useAcpSessionId();
  const canDelete = useAcpAgentCapabilities()?.sessionCapabilities?.delete != null;
  useEffect(() => {
    vscode.postMessage({
      type: "threads",
      activeId,
      canDelete,
      threads: threads.map((thread) => ({
        id: thread.id,
        title: thread.title,
        updatedAt: typeof thread.custom?.updatedAt === "string" ? thread.custom.updatedAt : undefined,
        isRunning: thread.isRunning,
      })),
    });
  }, [threads, activeId, canDelete]);
  useEffect(() => {
    const onMessage = (event: MessageEvent<{ type?: string; id?: string }>) => {
      switch (event.data?.type) {
        case "switch-thread":
          if (event.data.id) aui.threads.switchToThread(event.data.id);
          break;
        case "new-thread":
          aui.threads.switchToNewThread();
          break;
        case "delete-thread":
          if (event.data.id) aui.threads.item({ id: event.data.id }).delete();
          break;
        case "refresh-threads":
          void aui.threads.reload();
          break;
        case "collapse-all":
          collapseAll.toggle();
          break;
      }
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [aui]);
  return null;
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
          <>
            <main aria-label="Crow ACP Chat" data-host={settings.host} className="crow-chat-layout flex h-full min-h-0 min-w-0 flex-col">
              <Header error={error} />
              <div className="min-h-0 flex-1"><ChatThread /></div>
              <Footer />
            </main>
            <VscodeBridge />
          </>
        )}
      </ChatSession>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<StrictMode><App /></StrictMode>);
