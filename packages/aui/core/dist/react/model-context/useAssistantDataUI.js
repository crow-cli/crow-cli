import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useEffect } from "@assistant-ui/tap/react-shim";
import { useAui } from "@assistant-ui/store";
//#region src/react/model-context/useAssistantDataUI.ts
/**
* Registers a renderer for named `data` message parts while the component is
* mounted.
*
* @param dataUI - Data renderer registration, or `null` to skip registration.
*/
const useAssistantDataUI = (dataUI) => {
	const $ = c(7);
	const aui = useAui();
	let t0;
	if ($[0] !== aui || $[1] !== dataUI) {
		t0 = () => {
			if (!dataUI?.name || !dataUI?.render) return;
			return aui.dataRenderers.setDataUI(dataUI.name, dataUI.render);
		};
		$[0] = aui;
		$[1] = dataUI;
		$[2] = t0;
	} else t0 = $[2];
	const t1 = dataUI?.name;
	const t2 = dataUI?.render;
	let t3;
	if ($[3] !== aui || $[4] !== t1 || $[5] !== t2) {
		t3 = [
			aui,
			t1,
			t2
		];
		$[3] = aui;
		$[4] = t1;
		$[5] = t2;
		$[6] = t3;
	} else t3 = $[6];
	useEffect(t0, t3);
};
//#endregion
export { useAssistantDataUI };
