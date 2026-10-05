import { useAssistantTool } from "./useAssistantTool.js";
//#region src/react/model-context/makeAssistantTool.ts
/**
* Creates a React component that registers an assistant tool when rendered.
*
* Use this when exporting reusable tool modules that can be included in JSX
* rather than calling {@link useAssistantTool} directly.
*
* @param tool - Tool definition and name to register.
*
* @deprecated Use a toolkit with `Tools({ toolkit })` and register it via
* `AuiConfig({ tools: Tools({ toolkit }) })` on the provider's `config` prop instead. See
* https://assistant-ui.com/docs/migrations/toolkit-tools.
*/
const makeAssistantTool = (tool) => {
	const Tool = () => {
		useAssistantTool(tool);
		return null;
	};
	Tool.unstable_tool = tool;
	return Tool;
};
//#endregion
export { makeAssistantTool };
