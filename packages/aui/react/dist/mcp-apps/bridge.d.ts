import type { SandboxHostFrame } from "../sandbox-host/SandboxHost.js";
import { type McpAppBridgeHandlers, type McpAppHostContext, type McpAppHostInfo } from "./types.js";
export type McpAppBridgeFrame = SandboxHostFrame;
export type CreateMcpAppBridgeOptions = {
    frame: McpAppBridgeFrame;
    handlers?: McpAppBridgeHandlers | undefined;
    hostInfo?: McpAppHostInfo | undefined;
    hostContext?: McpAppHostContext | undefined;
};
export type McpAppBridge = {
    onMessage: (event: MessageEvent) => void;
    dispose: () => void;
    notifyToolInput: (input: unknown) => void;
    notifyToolResult: (result: unknown) => void;
    notifyHostContextChanged: (hostContext: McpAppHostContext) => void;
};
export declare function createMcpAppBridge(opts: CreateMcpAppBridgeOptions): McpAppBridge;