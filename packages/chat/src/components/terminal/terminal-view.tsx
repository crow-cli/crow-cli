/**
 * One xterm.js terminal, one `/pty` socket, one shell.
 *
 * The wire is the rust side's contract: binary frames are pty bytes in both
 * directions (a UTF-8 sequence can split across reads, so text frames would
 * corrupt it), text frames are JSON control — `hello` with the pid, `exit`,
 * `error` in, and `resize` out. The initial size rides on the query string so
 * the shell is born at the right width instead of reflowing a frame later.
 *
 * xterm.js is the emulator; nothing here parses VT. Closing the socket is how
 * a shell dies — the server kills the pty on disconnect — so unmounting this
 * component is the whole teardown.
 */
import { useEffect, useRef } from "react";
import { Terminal, type ITheme } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import "@xterm/xterm/css/xterm.css";
import { useTermStore, type TermState } from "@/lib/term-store";

const ptyUrl = (cols: number, rows: number) =>
  `${location.protocol === "https:" ? "wss:" : "ws:"}//${location.host}/pty?cols=${cols}&rows=${rows}`;

/**
 * The app's tokens are oklch in CSS; xterm hands them to a canvas, which needs
 * resolved values. So read them off <html>, where the theme attribute picks the
 * set — all four themes, not just the light/dark split.
 */
function readTheme(): ITheme {
  const css = getComputedStyle(document.documentElement);
  const token = (name: string) => css.getPropertyValue(name).trim();
  return {
    background: token("--background"),
    foreground: token("--foreground"),
    cursor: token("--foreground"),
    cursorAccent: token("--background"),
    selectionBackground: token("--accent"),
  };
}

type Control = { type: "hello" | "exit" | "error"; pid?: number; code?: number; error?: string };

export function TerminalView({ id, active }: { id: number; active: boolean }) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const termRef = useRef<Terminal | null>(null);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const term = new Terminal({
      cursorBlink: true,
      fontSize: 12,
      lineHeight: 1.2,
      fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
      theme: readTheme(),
    });
    const fit = new FitAddon();
    term.loadAddon(fit);
    term.open(host);
    termRef.current = term;
    fit.fit();

    const sent = { cols: term.cols, rows: term.rows };
    const ws = new WebSocket(ptyUrl(sent.cols, sent.rows));
    ws.binaryType = "arraybuffer";
    const setState = (state: TermState, pid?: number | null) =>
      useTermStore.getState().setState(id, state, pid);

    ws.onopen = () => term.focus();
    ws.onmessage = (message) => {
      if (typeof message.data !== "string") {
        term.write(new Uint8Array(message.data));
        return;
      }
      const control = JSON.parse(message.data) as Control;
      if (control.type === "hello") setState("live", control.pid ?? null);
      if (control.type === "exit") {
        setState("exited");
        term.write(`\r\n[shell exited${typeof control.code === "number" ? ` code ${control.code}` : ""}]\r\n`);
      }
      if (control.type === "error") {
        setState("dropped");
        term.write(`\r\n[${control.error}]\r\n`);
      }
    };
    ws.onclose = () => {
      // A tab the user closed is gone from the store already; this is the
      // server going away under a live tab.
      if (useTermStore.getState().tabs.some((tab) => tab.id === id && tab.state === "live")) {
        setState("dropped");
        term.write("\r\n[the /pty socket closed]\r\n");
      }
    };

    const encoder = new TextEncoder();
    const input = term.onData((data) => {
      if (ws.readyState === WebSocket.OPEN) ws.send(encoder.encode(data));
    });
    const resize = term.onResize(({ cols, rows }) => {
      if (cols === sent.cols && rows === sent.rows) return;
      sent.cols = cols;
      sent.rows = rows;
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "resize", cols, rows }));
      }
    });
    // Hidden tabs and a collapsed panel both measure zero; fitting there would
    // resize the pty to nothing. The observer fires again when there is real
    // height, and re-fits then.
    const observer = new ResizeObserver(() => {
      if (host.offsetParent && host.clientHeight > 0) fit.fit();
    });
    observer.observe(host);

    return () => {
      observer.disconnect();
      resize.dispose();
      input.dispose();
      ws.close();
      term.dispose();
      termRef.current = null;
    };
  }, [id]);

  // A theme change is a repaint, not a restart: re-opening the terminal would
  // kill the shell. The tokens live on <html>, so watch what picks them.
  useEffect(() => {
    const repaint = () => {
      const term = termRef.current;
      if (term) term.options.theme = readTheme();
    };
    const observer = new MutationObserver(repaint);
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["class", "data-theme"],
    });
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (active) termRef.current?.focus();
  }, [active]);

  return (
    <div
      ref={hostRef}
      data-testid={`term-${id}`}
      className="h-full w-full"
      style={{ display: active ? "block" : "none" }}
    />
  );
}
