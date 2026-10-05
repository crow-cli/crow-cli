import { useManagedRef } from "./useManagedRef.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import "@assistant-ui/tap/react-shim";
import { useCallbackRef } from "radix-ui/internal";
//#region src/utils/hooks/useOnResizeContent.ts
const useOnResizeContent = (callback) => {
	const $ = c(2);
	const callbackRef = useCallbackRef(callback);
	let t0;
	if ($[0] !== callbackRef) {
		t0 = (el) => {
			const resizeObserver = new ResizeObserver(() => {
				callbackRef();
			});
			const mutationObserver = new MutationObserver((mutations) => {
				if (mutations.some(_temp)) callbackRef();
			});
			resizeObserver.observe(el);
			mutationObserver.observe(el, {
				childList: true,
				subtree: true,
				attributes: true,
				characterData: true
			});
			return () => {
				resizeObserver.disconnect();
				mutationObserver.disconnect();
			};
		};
		$[0] = callbackRef;
		$[1] = t0;
	} else t0 = $[1];
	return useManagedRef(t0);
};
function _temp(m) {
	return m.type !== "attributes" || m.attributeName !== "style";
}
//#endregion
export { useOnResizeContent };
