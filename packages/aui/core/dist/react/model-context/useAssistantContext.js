import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useEffect, useInsertionEffect, useRef } from "@assistant-ui/tap/react-shim";
import { useAui } from "@assistant-ui/store";
//#region src/react/model-context/useAssistantContext.ts
const useAssistantContext = (config) => {
	const $ = c(7);
	const { getContext, disabled: t0 } = config;
	const disabled = t0 === void 0 ? false : t0;
	const aui = useAui();
	const getContextRef = useRef(getContext);
	let t1;
	let t2;
	if ($[0] !== getContext) {
		t1 = () => {
			getContextRef.current = getContext;
		};
		t2 = [getContext];
		$[0] = getContext;
		$[1] = t1;
		$[2] = t2;
	} else {
		t1 = $[1];
		t2 = $[2];
	}
	useInsertionEffect(t1, t2);
	let t3;
	let t4;
	if ($[3] !== aui || $[4] !== disabled) {
		t3 = () => {
			if (disabled) return;
			return aui.modelContext.register({ getModelContext: () => ({ system: getContextRef.current() }) });
		};
		t4 = [aui, disabled];
		$[3] = aui;
		$[4] = disabled;
		$[5] = t3;
		$[6] = t4;
	} else {
		t3 = $[5];
		t4 = $[6];
	}
	useEffect(t3, t4);
};
//#endregion
export { useAssistantContext };
