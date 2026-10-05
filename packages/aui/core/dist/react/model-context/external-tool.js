//#region src/react/model-context/external-tool.ts
/**
* Marks a generative toolkit entry as an externally executed backend tool.
*
* Use this when another system (for example a backend route or LangGraph node)
* already defines and executes the tool, but assistant-ui should render its
* tool calls. The use-generative compiler omits `execute: externalTool()`
* entries from the server build and keeps a `type: "backend"` renderer on the
* client build.
*/
function externalTool() {
	throw new Error("[assistant-ui] externalTool() has no runtime implementation - it marks a tool that executes outside assistant-ui and is stripped at build time by the use-generative compiler. Make sure this module is compiled as \"use generative\".");
}
//#endregion
export { externalTool };
