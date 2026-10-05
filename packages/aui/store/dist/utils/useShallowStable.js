import { shallowEqual } from "./shallow-equal.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useMemo, useRef } from "@assistant-ui/tap/react-shim";
//#region src/utils/useShallowStable.ts
const useShallowStable = (value) => {
	const cell = useMemo(() => ({}), []);
	if (cell.v !== void 0 && shallowEqual(cell.v, value)) return cell.v;
	cell.v = value;
	return value;
};
const useShallowSelector = (select) => {
	const $ = c(2);
	const previous = useRef(void 0);
	let t0;
	if ($[0] !== select) {
		t0 = (state) => {
			const next = select(state);
			if (previous.current !== void 0 && shallowEqual(previous.current, next)) return previous.current;
			previous.current = next;
			return next;
		};
		$[0] = select;
		$[1] = t0;
	} else t0 = $[1];
	return t0;
};
//#endregion
export { shallowEqual, useShallowSelector, useShallowStable };
