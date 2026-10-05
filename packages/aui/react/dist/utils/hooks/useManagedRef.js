import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useRef } from "@assistant-ui/tap/react-shim";
//#region src/utils/hooks/useManagedRef.ts
const useManagedRef = (callback) => {
	const $ = c(2);
	const cleanupRef = useRef(void 0);
	let t0;
	if ($[0] !== callback) {
		t0 = (el) => {
			if (cleanupRef.current) {
				cleanupRef.current();
				cleanupRef.current = void 0;
			}
			if (el) cleanupRef.current = callback(el);
		};
		$[0] = callback;
		$[1] = t0;
	} else t0 = $[1];
	return t0;
};
//#endregion
export { useManagedRef };
