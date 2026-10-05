import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useInsertionEffect, useRef } from "@assistant-ui/tap/react-shim";
//#region src/react/runtimes/assistant-transport/useLatestRef.ts
function useLatestRef(value) {
	const $ = c(3);
	const ref = useRef(value);
	let t0;
	let t1;
	if ($[0] !== value) {
		t0 = () => {
			ref.current = value;
		};
		t1 = [value];
		$[0] = value;
		$[1] = t0;
		$[2] = t1;
	} else {
		t0 = $[1];
		t1 = $[2];
	}
	useInsertionEffect(t0, t1);
	return ref;
}
//#endregion
export { useLatestRef };
