import type { Tool } from "assistant-stream";
export type Unstable_WebMcpProviderOptions = {
    filter?: (name: string, tool: Tool<any, any>) => boolean;
};
export type Unstable_WebMcpProviderResult = {
    status: "unsupported" | "active";
    registeredToolNames: readonly string[];
};
/**
 * Publishes the frontend tools in the model context to a WebMCP-capable
 * browser, so the user's own browser agent can call them.
 *
 * Returns `status: "unsupported"` when the page exposes no
 * `document.modelContext` (or `navigator.modelContext`), and the sorted names
 * of the tools currently registered with the host.
 */
export declare const unstable_useWebMcpProvider: (options?: Unstable_WebMcpProviderOptions) => Unstable_WebMcpProviderResult;