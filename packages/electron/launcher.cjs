"use strict";

// Pure helpers for the Electron launcher, kept free of `require("electron")`
// so `bun test` can exercise them without an Electron install.

const DEFAULT_ACP_URL = "ws://127.0.0.1:2769/acp";

/** Args to hand `child_process.spawn`, minus the binary. `--port 0` asks
 * crow-web to bind an ephemeral port and print the real one on stdout — that
 * line is what `parsePort` reads. */
function buildArgs(options = {}) {
  const { root, acpUrl, shell } = options;
  const args = ["--port", "0"];
  if (root) args.push("--root", root);
  if (acpUrl) args.push("--acp-url", acpUrl);
  if (shell) args.push("--shell", shell);
  return args;
}

/** crow-web prints `crow-web serving <root> on http://127.0.0.1:<port> ...`;
 * pull the port out of that line. */
function parsePort(line) {
  const match = /https?:\/\/[^:\s]+:(\d+)/.exec(line);
  return match ? Number(match[1]) : null;
}

/** The env-overridable pieces of a launch. Reading them here keeps main.cjs
 * about Electron, not about where the binary or the workspace lives. */
function launchOptions(overrides = {}) {
  return {
    bin: overrides.bin ?? process.env.CROW_WEB_BIN ?? "crow-web",
    root: overrides.root ?? process.env.CROW_ROOT ?? process.cwd(),
    acpUrl: overrides.acpUrl ?? process.env.CROW_ACP_URL ?? DEFAULT_ACP_URL,
    shell: overrides.shell ?? process.env.SHELL,
  };
}

module.exports = { DEFAULT_ACP_URL, buildArgs, parsePort, launchOptions };
