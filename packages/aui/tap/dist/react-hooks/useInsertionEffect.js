import { useEffectImpl } from "./useEffect.js";
//#region src/react-hooks/useInsertionEffect.ts
function useInsertionEffect(effect, deps) {
	useEffectImpl(effect, deps, "insertion");
}
//#endregion
export { useInsertionEffect };
