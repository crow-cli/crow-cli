import { useCallback, useState } from "react";
import { DEFAULT_MCP_CONFIG } from "@/lib/mcp-config";

/** Default ACP WebSocket endpoint, overridable from the header input. */
export const DEFAULT_ACP_URL = "ws://127.0.0.1:2771/acp";
export const DEFAULT_CWD = "/home/thomas/src/crow-web/crow-chat";

const ACP_KEY = "crow-chat.acp-url";
const CWD_KEY = "crow-chat.cwd";
const MCP_KEY = "crow-chat.mcp";
const SIDEBAR_KEY = "crow-chat.sidebar";

export function useAcpUrlSetting(): [string, (next: string) => void] {
  const [url, setUrl] = useState(
    () => localStorage.getItem(ACP_KEY) ?? DEFAULT_ACP_URL,
  );
  const save = useCallback((next: string) => {
    const value = next.trim() || DEFAULT_ACP_URL;
    localStorage.setItem(ACP_KEY, value);
    setUrl(value);
  }, []);
  return [url, save];
}

export function useCwdSetting(): [string, (next: string) => void] {
  const [cwd, setCwd] = useState(
    () => localStorage.getItem(CWD_KEY) ?? DEFAULT_CWD,
  );
  const save = useCallback((next: string) => {
    const value = next.trim() || DEFAULT_CWD;
    localStorage.setItem(CWD_KEY, value);
    setCwd(value);
  }, []);
  return [cwd, save];
}

/** The thread list rail, remembered across reloads and cwd switches. */
export function useSidebarSetting(): [boolean, (next: boolean) => void] {
  const [collapsed, setCollapsed] = useState(
    () => localStorage.getItem(SIDEBAR_KEY) === "collapsed",
  );
  const save = useCallback((next: boolean) => {
    localStorage.setItem(SIDEBAR_KEY, next ? "collapsed" : "expanded");
    setCollapsed(next);
  }, []);
  return [collapsed, save];
}

export function useMcpSetting(): [string, (next: string) => void] {
  const [text, setText] = useState(
    () => localStorage.getItem(MCP_KEY) ?? DEFAULT_MCP_CONFIG,
  );
  const save = useCallback((next: string) => {
    localStorage.setItem(MCP_KEY, next);
    setText(next);
  }, []);
  return [text, save];
}
