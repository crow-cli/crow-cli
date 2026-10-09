import * as vscode from "vscode";

type SessionRow = { id: string; title?: string; updatedAt?: string; isRunning: boolean };

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

/**
 * The sessions tree is fed by the chat webview, which owns the only ACP
 * connection: it posts its runtime's thread list and this mirrors it natively,
 * so the history lives in a real view (with real view/title and item menus)
 * instead of a second list inside the webview.
 */
class SessionProvider implements vscode.TreeDataProvider<SessionRow> {
  private rows: SessionRow[] = [];
  private activeId: string | undefined;
  private canDelete = false;
  private readonly change = new vscode.EventEmitter<SessionRow | undefined>();
  readonly onDidChangeTreeData = this.change.event;

  update(rows: SessionRow[], activeId: string | undefined, canDelete: boolean) {
    this.rows = rows;
    this.activeId = activeId;
    this.canDelete = canDelete;
    this.change.fire(undefined);
  }

  getChildren(): SessionRow[] {
    return this.rows;
  }

  getTreeItem(row: SessionRow): vscode.TreeItem {
    const item = new vscode.TreeItem(row.title || row.id, vscode.TreeItemCollapsibleState.None);
    item.description = relativeTime(row.updatedAt);
    item.tooltip = row.id;
    item.contextValue = this.canDelete ? "session" : "session-locked";
    item.iconPath = new vscode.ThemeIcon(row.isRunning ? "sync~spin" : row.id === this.activeId ? "comment-discussion" : "comment");
    item.command = { command: "crowAcp.session.open", title: "Open Session", arguments: [row.id] };
    return item;
  }
}

export function activate(context: vscode.ExtensionContext) {
  let panel: vscode.WebviewPanel | undefined;
  const webviews = new Map<vscode.Webview, { host: "editor" | "sidebar"; cleanup: vscode.Disposable }>();
  const sessions = new SessionProvider();
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
      } else if (payload.type === "threads" && Array.isArray(payload.threads)) {
        sessions.update(
          payload.threads as SessionRow[],
          typeof payload.activeId === "string" ? payload.activeId : undefined,
          payload.canDelete === true,
        );
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
    webviews.set(webview, { host, cleanup });
    render(webview, host);
  }
  function renderAll() {
    for (const [webview, { host }] of webviews) render(webview, host);
  }
  /** The sidebar webview when it is open, else whichever chat tab is — the
      tree mirrors that webview's thread list and commands answer to it. */
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
  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider("crowAcp.sidebar", {
      resolveWebviewView(view) {
        configure(view, "sidebar");
      },
    }, { webviewOptions: { retainContextWhenHidden: true } }),
    vscode.commands.registerCommand("crowAcp.openSidebar", () =>
      vscode.commands.executeCommand("crowAcp.sidebar.focus")),
    vscode.window.registerTreeDataProvider("crowAcp.sessions", sessions),
    vscode.commands.registerCommand("crowAcp.session.open", (id: string) => {
      postToChat({ type: "switch-thread", id });
      focusChat();
    }),
    vscode.commands.registerCommand("crowAcp.session.new", () => {
      postToChat({ type: "new-thread" });
      focusChat();
    }),
    vscode.commands.registerCommand("crowAcp.sessions.refresh", () =>
      postToChat({ type: "refresh-threads" })),
    vscode.commands.registerCommand("crowAcp.session.delete", async (row: SessionRow) => {
      const answer = await vscode.window.showWarningMessage(
        `Delete session ${row.title || row.id}? The agent forgets it. This cannot be undone.`,
        { modal: true },
        "Delete",
      );
      if (answer === "Delete") postToChat({ type: "delete-thread", id: row.id });
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
    { dispose: () => {
      panel?.dispose();
      for (const { cleanup } of webviews.values()) cleanup.dispose();
    } },
  );
}
