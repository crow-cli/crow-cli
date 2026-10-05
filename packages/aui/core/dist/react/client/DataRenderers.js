import { nullProtoRecord } from "../../utils/record.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useState } from "@assistant-ui/tap/react-shim";
import { resource } from "@assistant-ui/tap";
//#region src/react/client/DataRenderers.ts
/**
* Registers renderers for `data` message parts.
*
* Data renderers are looked up by the part's `name` field. Use this resource
* directly for a renderer scope, or prefer {@link useAssistantDataUI} /
* {@link makeAssistantDataUI} when registering from React components.
*/
const useDataRenderers = () => {
	const $ = c(4);
	const [state, setState] = useState(_temp);
	let t0;
	if ($[0] === Symbol.for("react.memo_cache_sentinel")) {
		t0 = (name, render) => {
			setState((prev) => {
				const renderers = nullProtoRecord(prev.renderers);
				renderers[name] = [...renderers[name] ?? [], render];
				return {
					...prev,
					renderers
				};
			});
			return () => {
				setState((prev_0) => {
					const renderers_0 = nullProtoRecord(prev_0.renderers);
					const remaining = renderers_0[name]?.filter((r) => r !== render) ?? [];
					if (remaining.length > 0) renderers_0[name] = remaining;
					else delete renderers_0[name];
					return {
						...prev_0,
						renderers: renderers_0
					};
				});
			};
		};
		$[0] = t0;
	} else t0 = $[0];
	const setDataUI = t0;
	let t1;
	if ($[1] === Symbol.for("react.memo_cache_sentinel")) {
		t1 = (render_0) => {
			setState((prev_1) => ({
				...prev_1,
				fallbacks: [...prev_1.fallbacks, render_0]
			}));
			return () => {
				setState((prev_2) => ({
					...prev_2,
					fallbacks: prev_2.fallbacks.filter((r_0) => r_0 !== render_0)
				}));
			};
		};
		$[1] = t1;
	} else t1 = $[1];
	const setFallbackDataUI = t1;
	let t2;
	if ($[2] !== state) {
		t2 = {
			getState: () => state,
			setDataUI,
			setFallbackDataUI
		};
		$[2] = state;
		$[3] = t2;
	} else t2 = $[3];
	return t2;
};
const DataRenderers = resource(useDataRenderers);
function _temp() {
	return {
		renderers: nullProtoRecord(),
		fallbacks: []
	};
}
//#endregion
export { DataRenderers };
