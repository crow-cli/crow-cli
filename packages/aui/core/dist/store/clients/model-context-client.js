import { CompositeContextProvider } from "../../utils/composite-context-provider.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useEffect, useState } from "@assistant-ui/tap/react-shim";
import { resource } from "@assistant-ui/tap";
import { shallowEqual } from "@assistant-ui/store/internal";
//#region src/store/clients/model-context-client.ts
const EMPTY_TOOL_NAMES = [];
const INITIAL_STATE = {
	modelName: void 0,
	toolNames: EMPTY_TOOL_NAMES
};
const toolNamesEqual = (a, b) => a === b || shallowEqual(a, b);
const deriveState = (composite, prev) => {
	const ctx = composite.getModelContext();
	const modelName = ctx.config?.modelName;
	const keys = ctx.tools ? Object.keys(ctx.tools).sort() : EMPTY_TOOL_NAMES;
	const toolNames = keys.length ? keys : EMPTY_TOOL_NAMES;
	if (modelName === prev.modelName && toolNamesEqual(toolNames, prev.toolNames)) return prev;
	return {
		modelName,
		toolNames
	};
};
const useModelContext = () => {
	const $ = c(11);
	let t0;
	if ($[0] === Symbol.for("react.memo_cache_sentinel")) {
		t0 = new CompositeContextProvider();
		$[0] = t0;
	} else t0 = $[0];
	const composite = t0;
	let t1;
	if ($[1] === Symbol.for("react.memo_cache_sentinel")) {
		t1 = () => deriveState(composite, INITIAL_STATE);
		$[1] = t1;
	} else t1 = $[1];
	const [state, setState] = useState(t1);
	let t2;
	let t3;
	if ($[2] === Symbol.for("react.memo_cache_sentinel")) {
		t2 = () => {
			setState((prev) => deriveState(composite, prev));
			return composite.subscribe(() => {
				setState((prev_0) => deriveState(composite, prev_0));
			});
		};
		t3 = [composite];
		$[2] = t2;
		$[3] = t3;
	} else {
		t2 = $[2];
		t3 = $[3];
	}
	useEffect(t2, t3);
	let t4;
	if ($[4] !== state) {
		t4 = () => deriveState(composite, state);
		$[4] = state;
		$[5] = t4;
	} else t4 = $[5];
	let t5;
	let t6;
	let t7;
	if ($[6] === Symbol.for("react.memo_cache_sentinel")) {
		t5 = () => composite.getModelContext();
		t6 = (callback) => composite.subscribe(callback);
		t7 = (provider) => composite.registerModelContextProvider(provider);
		$[6] = t5;
		$[7] = t6;
		$[8] = t7;
	} else {
		t5 = $[6];
		t6 = $[7];
		t7 = $[8];
	}
	let t8;
	if ($[9] !== t4) {
		t8 = {
			getState: t4,
			getModelContext: t5,
			subscribe: t6,
			register: t7
		};
		$[9] = t4;
		$[10] = t8;
	} else t8 = $[10];
	return t8;
};
const ModelContext = resource(useModelContext);
//#endregion
export { ModelContext };
