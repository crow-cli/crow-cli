import { type ReactNode } from "react";
import type { ToolCallMessagePart } from "@assistant-ui/core";
import type { ToolCallMessagePartComponent } from "@assistant-ui/core/react";
import { type ResourceElement } from "@assistant-ui/tap";
import type { McpAppBridgeHandlers, McpAppHostContext, McpAppHostInfo, McpAppSandboxConfig, McpAppsHost } from "./types.js";
/**
 * Options that apply to a single MCP app. `McpAppRenderer` takes them as
 * thread-wide defaults, and its `forPart` resolver overrides them for one part.
 */
export type McpAppPartOptions = {
    /** Sandbox + container styling. Passes through to SafeContentFrame. */
    sandbox?: McpAppSandboxConfig;
    /**
     * Upper bound (in pixels) applied to the widget-driven auto-resize height.
     * Defaults to 800.
     */
    maxHeight?: number;
    /** Identifies the host to the widget in the `ui/initialize` response. */
    hostInfo?: McpAppHostInfo;
    /** Delivered to the widget on initialize and pushed via `notifications/host_context/changed` on change. */
    hostContext?: McpAppHostContext;
    /**
     * Optional widget interaction and lifecycle handlers. Data-plane handlers
     * (`callTool`, `readResource`, `listResources`) always use `host`.
     *
     * Which handlers a widget may call is captured when its frame mounts, so a
     * `forPart` resolver returns the same handler keys for a part on every
     * render even when the implementations change.
     */
    handlers?: Omit<McpAppBridgeHandlers, "callTool" | "readResource" | "listResources">;
    /** Rendered when no MCP app is on the part, or while load is in flight / failed (unless overridden). */
    fallback?: ReactNode;
    /** Rendered while the resource is loading. Defaults to `fallback`. */
    loadingFallback?: ReactNode;
    /** Rendered when the resource load rejects. Defaults to `fallback`. */
    errorFallback?: ReactNode | ((error: Error) => ReactNode);
};
export type McpAppRendererOptions = McpAppPartOptions & {
    /**
     * Provides the data-plane operations the widget can request
     * (`loadResource`, `callTool`, `readResource`, `listResources`). Use
     * `McpAppsRemoteHost({ url })` for the default HTTP-route convention.
     */
    host: ResourceElement<McpAppsHost>;
    /**
     * Resolves the options for one part. Each returned value replaces the
     * thread-wide option of the same name, so a host can give every MCP app its
     * own display mode and answer `requestDisplayMode` for the part that asked.
     *
     * `handlers` is the exception and merges per key. Its keys are capabilities
     * negotiated with the widget rather than data, so replacing the whole bag to
     * add one handler would withdraw the others from that part's widget with
     * nothing to observe it by.
     */
    forPart?: (part: ToolCallMessagePart) => McpAppPartOptions;
};
export declare const McpAppRenderer: import("@assistant-ui/tap").Resource<{
    readonly render: ToolCallMessagePartComponent;
}, [options: McpAppRendererOptions]>;