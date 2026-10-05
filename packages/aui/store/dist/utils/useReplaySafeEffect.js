import { useEffect, useState } from "@assistant-ui/tap/react-shim";
//#region src/utils/useReplaySafeEffect.ts
const depsEqual = (a, b) => a.length === b.length && a.every((value, index) => Object.is(value, b[index]));
/** `useEffect` for a teardown that must survive a replay. Fast Refresh and a StrictMode double mount run an effect's cleanup and then its setup in the same tick with unchanged deps; both are skipped, so the work the effect started keeps running. A deps change still runs the old cleanup before the new setup, and an unmount or a hidden `<Activity>` runs the cleanup one microtask later. */
const useReplaySafeEffect = (effect, deps) => {
	const [cell] = useState(() => ({ pending: void 0 }));
	useEffect(() => {
		const pending = cell.pending;
		cell.pending = void 0;
		let current;
		if (pending !== void 0 && depsEqual(pending.deps, deps)) current = pending;
		else {
			pending?.cleanup?.();
			current = {
				deps,
				cleanup: effect()
			};
		}
		return () => {
			cell.pending = current;
			queueMicrotask(() => {
				if (cell.pending !== current) return;
				cell.pending = void 0;
				current.cleanup?.();
			});
		};
	}, deps);
};
//#endregion
export { useReplaySafeEffect };
