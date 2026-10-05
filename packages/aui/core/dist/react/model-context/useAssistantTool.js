import { isStandaloneToolDisplay, makeToolCallTextComponent } from "./toolbox.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useEffect } from "@assistant-ui/tap/react-shim";
import { useAui } from "@assistant-ui/store";
//#region src/react/model-context/useAssistantTool.ts
/**
* Registers a tool with the assistant model context while the component is
* mounted.
*
* If `render` is provided, it is also installed as the renderer for matching
* tool-call message parts. The registration is removed automatically when the
* component unmounts or the tool definition changes.
*
* Pass a referentially stable tool object, such as one declared at module
* scope or memoized with `useMemo`, to avoid re-registering on every render.
*
* @param tool - Tool definition and name to register.
*
* @deprecated Use a toolkit with `Tools({ toolkit })` and register it via
* `AuiConfig({ tools: Tools({ toolkit }) })` on the provider's `config` prop instead. See
* https://assistant-ui.com/docs/migrations/toolkit-tools.
*
* @example
* ```tsx
* const weatherTool = {
*   toolName: "get_weather",
*   type: "frontend",
*   description: "Get the weather for a city.",
*   parameters: weatherSchema,
*   execute: async ({ city }: { city: string }) => fetchWeather(city),
*   render: WeatherToolUI,
* } satisfies AssistantToolProps<{ city: string }, Weather>;
*
* function WeatherToolRegistration() {
*   useAssistantTool(weatherTool);
*   return null;
* }
* ```
*/
const useAssistantTool = (tool) => {
	const $ = c(20);
	const aui = useAui();
	let t0;
	if ($[0] !== tool) {
		t0 = isStandaloneToolDisplay(tool);
		$[0] = tool;
		$[1] = t0;
	} else t0 = $[1];
	const standalone = t0;
	let t1;
	if ($[2] !== tool.renderText) {
		t1 = tool.renderText ? makeToolCallTextComponent(tool.renderText) : void 0;
		$[2] = tool.renderText;
		$[3] = t1;
	} else t1 = $[3];
	const renderTextComponent = t1;
	const render = tool.render ?? renderTextComponent;
	let t2;
	if ($[4] !== aui.tools || $[5] !== render || $[6] !== standalone || $[7] !== tool.toolName) {
		t2 = () => {
			if (!render) return;
			return aui.tools.setToolUI(tool.toolName, render, { standalone });
		};
		$[4] = aui.tools;
		$[5] = render;
		$[6] = standalone;
		$[7] = tool.toolName;
		$[8] = t2;
	} else t2 = $[8];
	let t3;
	if ($[9] !== aui || $[10] !== render || $[11] !== standalone || $[12] !== tool.toolName) {
		t3 = [
			aui,
			tool.toolName,
			render,
			standalone
		];
		$[9] = aui;
		$[10] = render;
		$[11] = standalone;
		$[12] = tool.toolName;
		$[13] = t3;
	} else t3 = $[13];
	useEffect(t2, t3);
	let t4;
	if ($[14] !== aui.modelContext || $[15] !== tool) {
		t4 = () => {
			const { toolName, render: render_0, renderText, display, ...rest } = tool;
			const context = { tools: { [toolName]: rest } };
			return aui.modelContext.register({ getModelContext: () => context });
		};
		$[14] = aui.modelContext;
		$[15] = tool;
		$[16] = t4;
	} else t4 = $[16];
	let t5;
	if ($[17] !== aui || $[18] !== tool) {
		t5 = [aui, tool];
		$[17] = aui;
		$[18] = tool;
		$[19] = t5;
	} else t5 = $[19];
	useEffect(t4, t5);
};
//#endregion
export { useAssistantTool };
