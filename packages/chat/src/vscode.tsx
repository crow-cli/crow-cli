import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { useAcpAgentCapabilities, useAcpSessionId } from "@assistant-ui/acp";
import { useAui, useAuiState } from "@assistant-ui/react";
import { ChatSession, ChatThread } from "@/components/chat-session";
import { ModelSelector } from "@/components/model-selector";
import { ContextGauge } from "@/components/context-meter";
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
};
const mcp = parseMcpConfig(settings.mcpConfig);

/**
 * Model and context ride the composer's action row instead of a footer, so the
 * thread gets every vertical pixel. Narrower than the standalone app's copy:
 * a sidebar has no room for the full-width selector.
 */
function ComposerStatus() {
  return (
    <>
      <ModelSelector className="max-w-40" />
      <ContextGauge />
    </>
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
              {error && <p role="alert" className="text-destructive border-b px-3 py-1.5 text-xs">{error}</p>}
              <div className="min-h-0 flex-1"><ChatThread composerStatus={ComposerStatus} /></div>
            </main>
            <VscodeBridge />
          </>
        )}
      </ChatSession>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<StrictMode><App /></StrictMode>);
