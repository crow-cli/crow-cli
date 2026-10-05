import { useAssistantToolUI } from "./useAssistantToolUI.js";
//#region src/react/model-context/makeAssistantToolUI.ts
/**
* Creates a React component that registers a tool-call renderer when rendered.
*
* Use this to package reusable display components for tools whose definitions
* are registered elsewhere.
*
* @param tool - Tool renderer registration.
*
* @deprecated Put `render`/`renderText` on the matching toolkit entry, or use
* `MessagePrimitive.Parts` inline tool render overrides for per-message UI.
* See https://assistant-ui.com/docs/migrations/toolkit-tools.
*/
const makeAssistantToolUI = (tool) => {
	const ToolUI = () => {
		useAssistantToolUI(tool);
		return null;
	};
	ToolUI.unstable_tool = tool;
	return ToolUI;
};
//#endregion
export { makeAssistantToolUI };
