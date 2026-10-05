import { useEffect } from "./useEffect.js";
//#region src/react-hooks/useImperativeHandle.ts
const useImperativeHandle = (ref, create, deps) => {
	const attach = () => {
		if (!ref) return void 0;
		const value = create();
		if (typeof ref === "function") {
			const dispose = ref(value);
			return typeof dispose === "function" ? dispose : () => ref(null);
		}
		ref.current = value;
		return () => {
			ref.current = null;
		};
	};
	if (deps == null) useEffect(attach);
	else useEffect(attach, [...deps, ref]);
};
//#endregion
export { useImperativeHandle };
