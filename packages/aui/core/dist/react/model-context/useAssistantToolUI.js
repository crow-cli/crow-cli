import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useEffect } from "@assistant-ui/tap/react-shim";
import { useAui } from "@assistant-ui/store";
//#region src/react/model-context/useAssistantToolUI.ts
/**
* Registers a tool-call renderer while the component is mounted.
*
* This only affects rendering. Pair it with {@link Tools} or a backend tool
* registry to expose the actual tool definition to the model.
*
* @param tool - Tool renderer registration, or `null` to skip registration.
*
* @deprecated Put `render`/`renderText` on the matching toolkit entry, or use
* `MessagePrimitive.Parts` inline tool render overrides for per-message UI.
* See https://assistant-ui.com/docs/migrations/toolkit-tools.
*/
const useAssistantToolUI = (tool) => {
	const $ = c(9);
	const aui = useAui();
	const standalone = tool?.display === "standalone";
	let t0;
	if ($[0] !== aui || $[1] !== standalone || $[2] !== tool) {
		t0 = () => {
			if (!tool?.toolName || !tool?.render) return;
			return aui.tools.setToolUI(tool.toolName, tool.render, { standalone });
		};
		$[0] = aui;
		$[1] = standalone;
		$[2] = tool;
		$[3] = t0;
	} else t0 = $[3];
	const t1 = tool?.toolName;
	const t2 = tool?.render;
	let t3;
	if ($[4] !== aui || $[5] !== standalone || $[6] !== t1 || $[7] !== t2) {
		t3 = [
			aui,
			t1,
			t2,
			standalone
		];
		$[4] = aui;
		$[5] = standalone;
		$[6] = t1;
		$[7] = t2;
		$[8] = t3;
	} else t3 = $[8];
	useEffect(t0, t3);
};
//#endregion
export { useAssistantToolUI };
