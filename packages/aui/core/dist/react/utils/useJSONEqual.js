import { isJSONValueEqual } from "../../utils/json/is-json-equal.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useRef } from "@assistant-ui/tap/react-shim";
//#region src/react/utils/useJSONEqual.ts
function useJSONEqualValue(value) {
	const prev = useRef(value);
	if (prev.current !== value && !isJSONValueEqual(prev.current, value)) prev.current = value;
	return prev.current;
}
/**
* Like `useShallow`, but with JSON deep-equality. Use when a selector derives an
* equal-but-fresh value on every store update — e.g. folding over
* `thread.messages`, whose identity changes on every streaming token — where a
* shallow compare would re-render regardless.
*/
function useJSONEqual(selector) {
	const $ = c(2);
	const prev = useRef(void 0);
	let t0;
	if ($[0] !== selector) {
		t0 = (state) => {
			const next = selector(state);
			if (prev.current !== void 0 && isJSONValueEqual(prev.current, next)) return prev.current;
			prev.current = next;
			return next;
		};
		$[0] = selector;
		$[1] = t0;
	} else t0 = $[1];
	return t0;
}
//#endregion
export { useJSONEqual, useJSONEqualValue };
