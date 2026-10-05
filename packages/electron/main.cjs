"use strict";

const { spawn } = require("node:child_process");
const { app, BrowserWindow } = require("electron");
const { buildArgs, parsePort, launchOptions } = require("./launcher.cjs");

let server = null;
let serverPort = null;

function openWindow() {
  const win = new BrowserWindow({
    width: 1280,
    height: 800,
    title: "crow",
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  win.loadURL(`http://127.0.0.1:${serverPort}/`);
  return win;
}

/** Spawn crow-web on an ephemeral port and resolve once it prints its
 * `http://127.0.0.1:<port>` line. */
function startServer() {
  return new Promise((resolve, reject) => {
    const { bin, ...options } = launchOptions();
    const child = spawn(bin, buildArgs(options), {
      stdio: ["ignore", "pipe", "inherit"],
    });

    let settled = false;
    let buffered = "";
    const fail = (error) => {
      if (settled) return;
      settled = true;
      reject(error);
    };

    child.stdout.setEncoding("utf8");
    child.stdout.on("data", (chunk) => {
      buffered += chunk;
      const lines = buffered.split("\n");
      buffered = lines.pop() ?? "";
      for (const line of lines) {
        const port = parsePort(line);
        if (port !== null) {
          settled = true;
          resolve({ child, port });
          return;
        }
      }
    });
    child.once("error", fail);
    child.once("exit", (code) => fail(new Error(`crow-web exited early (code ${code})`)));
  });
}

app.whenReady().then(async () => {
  try {
    const { child, port } = await startServer();
    server = child;
    serverPort = port;
    openWindow();
  } catch (error) {
    console.error("failed to start crow-web:", error);
    app.quit();
  }
});

app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0 && serverPort !== null) {
    openWindow();
  }
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

app.on("quit", () => {
  if (server) server.kill();
});
