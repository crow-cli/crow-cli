import * as vscode from "vscode";

type SessionRow = { id: string; title?: string; updatedAt?: string; isRunning: boolean };
type SessionState = { rows: SessionRow[]; activeId?: string; canDelete: boolean };

function relativeTime(iso?: string): string | undefined {
  if (!iso) return undefined;
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return undefined;
  const minutes = Math.max(0, Math.round((Date.now() - then) / 60000));
  if (minutes < 1) return "now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

/** One row of the session dropdown: a session, or the new-session action. */
type SessionItem = vscode.QuickPickItem & { row?: SessionRow; isNew?: boolean };

const DELETE_BUTTON: vscode.QuickInputButton = { iconPath: new vscode.ThemeIcon("trash"), tooltip: "Delete Session" };

/**
 * The dropdown's contents. The chat webview owns the only ACP connection, so it
 * posts its runtime's thread list and this mirrors it into a quick pick — the
 * session menu lives in the view title, on the same row VS Code puts Copilot's
 * actions, instead of a second view stacked under the chat.
 */
function sessionItems(state: SessionState): SessionItem[] {
  const items: SessionItem[] = [{ label: "New Session", iconPath: new vscode.ThemeIcon("add"), isNew: true }];
  if (state.rows.length) items.push({ label: "Sessions", kind: vscode.QuickPickItemKind.Separator });
  for (const row of state.rows) {
    const active = row.id === state.activeId;
    items.push({
      label: row.title || row.id,
      description: [active ? "active" : undefined, relativeTime(row.updatedAt)].filter(Boolean).join(" · "),
      detail: row.id,
      iconPath: new vscode.ThemeIcon(row.isRunning ? "sync~spin" : active ? "comment-discussion" : "comment"),
      buttons: state.canDelete ? [DELETE_BUTTON] : [],
      row,
    });
  }
  return items;
}

export function activate(context: vscode.ExtensionContext) {
  let panel: vscode.WebviewPanel | undefined;
  type ChatEntry = { host: "editor" | "sidebar"; cleanup: vscode.Disposable; sessions: SessionState };
  const webviews = new Map<vscode.Webview, ChatEntry>();
  /** Fires with the webview whose thread list just changed, so an open
   * dropdown re-renders against the agent's answer instead of going stale. */
  const sessionsChanged = new vscode.EventEmitter<vscode.Webview>();
  const root = vscode.Uri.joinPath(context.extensionUri, "dist", "webview");
  function render(webview: vscode.Webview, host: "editor" | "sidebar") {
    const config = vscode.workspace.getConfiguration("crowAcp");
    const folder = vscode.window.activeTextEditor
      ? vscode.workspace.getWorkspaceFolder(vscode.window.activeTextEditor.document.uri)
      : undefined;
    const cwd = config.get<string>("cwd") || (folder ?? vscode.workspace.workspaceFolders?.[0])?.uri.fsPath;
    if (!cwd) {
      webview.html = '<html><body><p>Open a workspace folder or set <code>crowAcp.cwd</code> to use Crow ACP Chat.</p></body></html>';
      return;
    }
    const uri = (file: string) => webview.asWebviewUri(vscode.Uri.joinPath(root, file));
    const settings = JSON.stringify({
      host,
      endpoint: config.get<string>("endpoint"),
      cwd,
      protocol: config.get<string>("protocol"),
      mcpConfig: config.get<string>("mcpConfig"),
      accessibilityVerbosity: config.get<boolean>("accessibilityVerbosity"),
    }).replace(/</g, "\\u003c");
    const nonce = Array.from({ length: 24 }, () => Math.floor(Math.random() * 36).toString(36)).join("");
    webview.html = `<!DOCTYPE html>
<html><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'nonce-${nonce}' ${webview.cspSource}; style-src ${webview.cspSource} 'unsafe-inline'; font-src ${webview.cspSource} data:; img-src ${webview.cspSource} data: blob:; connect-src ws: wss:;">
<base href="${uri("")}/"><link rel="stylesheet" href="${uri("chat.css")}">
<title>Crow ACP Chat</title></head><body>
<script id="crow-acp-settings" type="application/json">${settings}</script>
<div id="root"></div><script nonce="${nonce}" type="module" src="${uri("chat.js")}"></script>
</body></html>`;
  }
  function configure(owner: vscode.WebviewPanel | vscode.WebviewView, host: "editor" | "sidebar") {
    const webview = owner.webview;
    webview.options = { enableScripts: true, localResourceRoots: [root] };
    const listener = webview.onDidReceiveMessage((message: unknown) => {
      if (typeof message !== "object" || message === null || !("type" in message)) return;
      const payload = message as { type: unknown; threads?: unknown; activeId?: unknown; canDelete?: unknown };
      if (payload.type === "settings") {
        void vscode.commands.executeCommand("workbench.action.openSettings", "@ext:crow-ai.crow-acp");
      } else if (payload.type === "pick-session") {
        pickSession(webview);
      } else if (payload.type === "threads" && Array.isArray(payload.threads)) {
        entry.sessions = {
          rows: payload.threads as SessionRow[],
          activeId: typeof payload.activeId === "string" ? payload.activeId : undefined,
          canDelete: payload.canDelete === true,
        };
        sessionsChanged.fire(webview);
      }
    });
    const disposal = owner.onDidDispose(() => {
      if (host === "editor") panel = undefined;
      cleanup.dispose();
    });
    const cleanup = new vscode.Disposable(() => {
      listener.dispose();
      disposal.dispose();
      webviews.delete(webview);
    });
    const entry: ChatEntry = { host, cleanup, sessions: { rows: [], canDelete: false } };
    webviews.set(webview, entry);
    render(webview, host);
  }
  function renderAll() {
    for (const [webview, { host }] of webviews) render(webview, host);
  }
  /** The sidebar webview when it is open, else whichever chat tab is — the
      dropdown mirrors that webview's thread list and commands answer to it. */
  function chatWebview(): vscode.Webview | undefined {
    for (const [webview, { host }] of webviews) if (host === "sidebar") return webview;
    return webviews.keys().next().value;
  }
  function postToChat(message: Record<string, unknown>) {
    chatWebview()?.postMessage(message);
  }
  function focusChat() {
    void vscode.commands.executeCommand("crowAcp.sidebar.focus");
  }
  /** The session dropdown behind the view title's history icon: new, switch
      and delete in one quick pick, live-updating while it is open. */
  function pickSession(webview: vscode.Webview) {
    const entry = webviews.get(webview);
    if (!entry) return;
    const pick = vscode.window.createQuickPick<SessionItem>();
    const sync = () => {
      const { rows, activeId } = entry.sessions;
      pick.items = sessionItems(entry.sessions);
      pick.placeholder = rows.length ? "Switch session, start a new one, or delete one" : "No sessions yet — start one";
      const title = rows.find((row) => row.id === activeId)?.title;
      pick.title = title ? `Crow Sessions — ${title}` : "Crow Sessions";
    };
    sync();
    pick.matchOnDescription = true;
    pick.buttons = [{ iconPath: new vscode.ThemeIcon("refresh"), tooltip: "Refresh Sessions" }];
    const changed = sessionsChanged.event((source) => {
      if (source === webview) sync();
    });
    pick.onDidTriggerButton(() => {
      void webview.postMessage({ type: "refresh-threads" });
    });
    pick.onDidTriggerItemButton(async ({ item }) => {
      if (!item.row) return;
      const answer = await vscode.window.showWarningMessage(
        `Delete session ${item.row.title || item.row.id}? The agent forgets it. This cannot be undone.`,
        { modal: true },
        "Delete",
      );
      if (answer === "Delete") void webview.postMessage({ type: "delete-thread", id: item.row.id });
    });
    pick.onDidAccept(() => {
      const [item] = pick.selectedItems;
      pick.hide();
      if (item?.isNew) void webview.postMessage({ type: "new-thread" });
      else if (item?.row && item.row.id !== entry.sessions.activeId) void webview.postMessage({ type: "switch-thread", id: item.row.id });
      if (entry.host === "sidebar") focusChat();
    });
    pick.onDidHide(() => {
      changed.dispose();
      pick.dispose();
    });
    pick.show();
  }
  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider("crowAcp.sidebar", {
      resolveWebviewView(view) {
        configure(view, "sidebar");
      },
    }, { webviewOptions: { retainContextWhenHidden: true } }),
    vscode.commands.registerCommand("crowAcp.openSidebar", () =>
      vscode.commands.executeCommand("crowAcp.sidebar.focus")),
    vscode.commands.registerCommand("crowAcp.session.new", () => {
      postToChat({ type: "new-thread" });
      focusChat();
    }),
    vscode.commands.registerCommand("crowAcp.session.switch", () => {
      const webview = chatWebview();
      if (webview) pickSession(webview);
      else focusChat();
    }),
    vscode.commands.registerCommand("crowAcp.collapseAll", () => {
      for (const webview of webviews.keys()) webview.postMessage({ type: "collapse-all" });
    }),
    vscode.commands.registerCommand("crowAcp.settings", () =>
      vscode.commands.executeCommand("workbench.action.openSettings", "@ext:crow-ai.crow-acp")),
    vscode.commands.registerCommand("crowAcp.open", () => {
      if (panel) { panel.reveal(); return; }
      panel = vscode.window.createWebviewPanel("crowAcp.chat", "Crow ACP Chat", vscode.ViewColumn.Beside, {
        retainContextWhenHidden: true,
      });
      configure(panel, "editor");
    }),
    vscode.workspace.onDidChangeConfiguration((event) => {
      if (event.affectsConfiguration("crowAcp")) renderAll();
    }),
    vscode.workspace.onDidChangeWorkspaceFolders(renderAll),
    sessionsChanged,
    { dispose: () => {
      panel?.dispose();
      for (const { cleanup } of webviews.values()) cleanup.dispose();
    } },
  );
}
