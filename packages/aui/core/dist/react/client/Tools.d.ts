import { type ResourceElement } from "@assistant-ui/tap";
import type { ClientOutput } from "@assistant-ui/store";
import type { McpAppResourceOutput } from "../types/scopes/tools.js";
import { type Toolkit } from "../model-context/toolbox.js";
export type { McpAppResourceOutput };
export declare const Tools: import("@assistant-ui/tap").Resource<ClientOutput<"tools">, [{
    /** Tools to expose to the model and optional renderers to install. */
    toolkit?: Toolkit;
    /** Optional MCP app resource whose tools should be merged into context. */
    mcpApp?: ResourceElement<McpAppResourceOutput> | undefined;
}]>;