import { type Tool } from "assistant-stream";
import type { WebMcpCallToolResult, WebMcpToolDescriptor } from "./webmcp-host.js";
/**
 * The predicate the WebMCP provider uses when no `filter` is passed: an enabled
 * frontend tool with a client-side `execute`. A tool authored without a `type`
 * is included, because `execute` is what distinguishes the deprecated
 * type-less form from a backend or human tool. A `filter` replaces this, so
 * pass it through to narrow the default set rather than widen it.
 */
export declare const defaultWebMcpFilter: (_name: string, tool: Tool<any, any>) => boolean;
export declare const toWebMcpInputSchema: (tool: Tool<any, any>) => unknown;
export declare const toMcpContent: (result: unknown, options: {
    tool: Tool<any, any>;
    toolCallId: string;
    args: Record<string, unknown>;
}) => Promise<WebMcpCallToolResult>;
export declare const toWebMcpTool: (name: string, getTool: () => Tool<any, any>, lifecycleSignal?: AbortSignal) => WebMcpToolDescriptor;