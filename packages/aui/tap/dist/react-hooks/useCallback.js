import { useMemo } from "./useMemo.js";
//#region src/react-hooks/useCallback.ts
const useCallback = (fn, deps) => {
	return useMemo(() => fn, deps);
};
//#endregion
export { useCallback };
