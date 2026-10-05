import type { Tool } from "assistant-stream";
import type { WebMcpHost } from "./webmcp-host.js";
export type WebMcpRegistrationProps = {
    host: WebMcpHost;
    name: string;
    /** Re-registers when it changes; an execute-only edit reads through instead. */
    signature: string;
    tool: Tool<any, any>;
    getCurrentTool: (name: string) => Tool<any, any> | undefined;
};
export declare const WebMcpRegistrationResource: import("@assistant-ui/tap").Resource<string | null, [WebMcpRegistrationProps]>;