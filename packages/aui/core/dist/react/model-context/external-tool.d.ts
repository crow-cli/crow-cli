/**
 * Marks a generative toolkit entry as an externally executed backend tool.
 *
 * Use this when another system (for example a backend route or LangGraph node)
 * already defines and executes the tool, but assistant-ui should render its
 * tool calls. The use-generative compiler omits `execute: externalTool()`
 * entries from the server build and keeps a `type: "backend"` renderer on the
 * client build.
 */
export declare function externalTool(): never;