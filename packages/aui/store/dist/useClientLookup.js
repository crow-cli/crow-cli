import { ClientResource } from "./useClientResource.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import "@assistant-ui/tap/react-shim";
import { useResources, withKey } from "@assistant-ui/tap";
//#region src/useClientLookup.ts
const getElementKey = (el) => {
	if (el.key === void 0) throw new Error("useClientLookup: Element has no key");
	return el.key;
};
function useClientLookup(elements) {
	const $ = c(12);
	let t0;
	if ($[0] !== elements) {
		t0 = elements.map(_temp);
		$[0] = elements;
		$[1] = t0;
	} else t0 = $[1];
	const resources = useResources(t0);
	let t1;
	if ($[2] !== elements) {
		t1 = elements.reduce(_temp2, Object.create(null));
		$[2] = elements;
		$[3] = t1;
	} else t1 = $[3];
	const keyToIndex = t1;
	let t2;
	if ($[4] !== resources) {
		t2 = resources.map(_temp3);
		$[4] = resources;
		$[5] = t2;
	} else t2 = $[5];
	const state = t2;
	let t3;
	if ($[6] !== keyToIndex || $[7] !== resources) {
		t3 = (lookup) => {
			if ("index" in lookup) {
				if (lookup.index < 0 || lookup.index >= resources.length) throw new Error(`useClientLookup: index ${lookup.index} out of bounds (length: ${resources.length}) (ignore if recovered)`);
				return resources[lookup.index].methods;
			}
			const index_0 = keyToIndex[lookup.key];
			if (index_0 === void 0) throw new Error(`useClientLookup: key "${lookup.key}" not found (ignore if recovered)`);
			return resources[index_0].methods;
		};
		$[6] = keyToIndex;
		$[7] = resources;
		$[8] = t3;
	} else t3 = $[8];
	let t4;
	if ($[9] !== state || $[10] !== t3) {
		t4 = {
			state,
			get: t3
		};
		$[9] = state;
		$[10] = t3;
		$[11] = t4;
	} else t4 = $[11];
	return t4;
}
function _temp3(r) {
	return r.state;
}
function _temp2(acc, element, index) {
	acc[getElementKey(element)] = index;
	return acc;
}
function _temp(el) {
	return withKey(getElementKey(el), ClientResource(el), el.deps);
}
//#endregion
export { useClientLookup };
