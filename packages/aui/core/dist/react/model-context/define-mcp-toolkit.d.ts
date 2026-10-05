import type { McpServerConfig } from "assistant-stream";
import type { Toolkit } from "./toolbox.js";
export type McpToolkitEntry = McpServerConfig | {
    server: McpServerConfig;
    disabled?: boolean | undefined;
    /**
     * Prefix applied to every tool name exposed by this MCP server. Useful
     * when multiple servers publish the same tool name, such as `search`.
     */
    prefix?: string | undefined;
    tools?: Record<string, McpToolkitToolConfig> | undefined;
};
export type McpToolkitToolConfig = {
    disabled?: boolean | undefined;
};
export type McpToolkitDefinition = Record<string, McpToolkitEntry>;
/**
 * Defines MCP server tools as a spreadable toolkit fragment. Pass a raw
 * `McpServerConfig` for always-on servers, or `{ server, disabled, tools }`
 * when a server should stay configured but not expose all tools for the current
 * request.
 */
export declare function defineMcpToolkit(definition: McpToolkitDefinition): Toolkit;