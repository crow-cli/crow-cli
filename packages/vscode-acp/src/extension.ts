import * as vscode from "vscode";

export function activate(context: vscode.ExtensionContext) {
  let panel: vscode.WebviewPanel | undefined;
  const webviews = new Map<vscode.Webview, { host: "editor" | "sidebar"; cleanup: vscode.Disposable }>();
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
      if (typeof message === "object" && message !== null && "type" in message && message.type === "settings") {
        void vscode.commands.executeCommand("workbench.action.openSettings", "@ext:crow-ai.crow-acp");
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
  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider("crowAcp.sidebar", {
      resolveWebviewView(view) {
        configure(view, "sidebar");
      },
    }, { webviewOptions: { retainContextWhenHidden: true } }),
    vscode.commands.registerCommand("crowAcp.openSidebar", () =>
      vscode.commands.executeCommand("crowAcp.sidebar.focus")),
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
