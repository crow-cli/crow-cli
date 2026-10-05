"use client";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useEffect, useState } from "@assistant-ui/tap/react-shim";
//#region src/unstable/useModelContextSnapshot.ts
/**
* `getModelContext()` rebuilds its result on every call, so a projection of the
* fields a consumer observes is held in state and refreshed on notification
* rather than read during render. Keeping the previous reference for an equal
* projection is what stops a notification carrying no observable change from
* invalidating everything derived from it.
*/
const useModelContextSnapshot = (aui, enabled, source) => {
	const $ = c(9);
	let t0;
	if ($[0] !== aui || $[1] !== enabled || $[2] !== source) {
		t0 = () => enabled ? source.read(aui) : source.empty;
		$[0] = aui;
		$[1] = enabled;
		$[2] = source;
		$[3] = t0;
	} else t0 = $[3];
	const [snapshot, setSnapshot] = useState(t0);
	let t1;
	let t2;
	if ($[4] !== aui || $[5] !== enabled || $[6] !== source) {
		t1 = () => {
			if (!enabled) return;
			const read = () => {
				const next = source.read(aui);
				setSnapshot((previous) => source.isEqual?.(previous, next) ? previous : next);
			};
			read();
			return source.subscribe(aui, read);
		};
		t2 = [
			aui,
			enabled,
			source
		];
		$[4] = aui;
		$[5] = enabled;
		$[6] = source;
		$[7] = t1;
		$[8] = t2;
	} else {
		t1 = $[7];
		t2 = $[8];
	}
	useEffect(t1, t2);
	return snapshot;
};
/** Shallow own-key comparison, for a projection whose values are records. */
const shallowEqualRecords = (previous, next) => {
	const keys = Object.keys(previous);
	if (keys.length !== Object.keys(next).length) return false;
	return keys.every((key) => Object.hasOwn(next, key) && previous[key] === next[key]);
};
//#endregion
export { shallowEqualRecords, useModelContextSnapshot };
