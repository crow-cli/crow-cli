import { resolveToolCallText } from "../../model-context/tool-call-text.js";
//#region src/react/model-context/toolbox.ts
/**
* Resolves whether a tool's UI should be presented standalone (outside the
* chain-of-thought grouping), applying the type-based defaults.
*
* An explicit `display` wins. Otherwise `human` tools default to standalone
* (they prompt the user), and every other tool defaults to inline (a trace of
* what the model is doing). MCP-app tool calls are detected separately from
* the part itself and are not resolved here.
*/
const isStandaloneToolDisplay = (tool) => {
	if (tool.display !== void 0) return tool.display === "standalone";
	return tool.type === "human";
};
const makeToolCallTextComponent = (text) => {
	return function ToolCallTextComponent(part) {
		return resolveToolCallText(text, part);
	};
};
//#endregion
export { isStandaloneToolDisplay, makeToolCallTextComponent };
