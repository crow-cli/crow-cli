import { depsShallowEqual } from "./depsShallowEqual.js";
import { useEffect, useRef } from "@assistant-ui/tap/react-shim";
//#region src/hooks/utils/useRenderMemo.ts
const useRenderMemo = (callback, deps, disableMemo) => {
	const stateRef = useRef(null);
	const state = stateRef.current ?? (stateRef.current = {
		currentDeps: null,
		current: null
	});
	const value = !disableMemo && state.currentDeps && depsShallowEqual(state.currentDeps, deps) ? state.current : callback();
	useEffect(() => {
		state.currentDeps = deps;
		state.current = value;
	});
	return value;
};
//#endregion
export { useRenderMemo };
