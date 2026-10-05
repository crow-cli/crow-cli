import { getCurrentResourceFiber } from "../core/helpers/execution-context.js";
import { isDevelopment } from "../core/helpers/env.js";
import { useEffect } from "./useEffect.js";
import { useRef } from "./useRef.js";
import { useReducer } from "./useReducer.js";
import { useEffectEvent } from "./useEffectEvent.js";
//#region src/react-hooks/useSyncExternalStore.ts
let didWarnUncachedGetSnapshot = false;
const useSyncExternalStore = (subscribe, getSnapshot, getServerSnapshot = getSnapshot) => {
	const isNeverMounted = getCurrentResourceFiber().isNeverMounted;
	const value = isNeverMounted ? getServerSnapshot() : getSnapshot();
	if (isDevelopment && !didWarnUncachedGetSnapshot && (!isNeverMounted || getServerSnapshot === getSnapshot)) {
		if (!Object.is(value, getSnapshot())) {
			didWarnUncachedGetSnapshot = true;
			console.error("The result of getSnapshot should be cached to avoid an infinite loop");
		}
	}
	const [, forceUpdate] = useReducer((c) => c + 1, 0);
	const commitCheckDepth = useRef(0);
	const checkForUpdates = useEffectEvent(() => {
		try {
			if (Object.is(value, getSnapshot())) {
				commitCheckDepth.current = 0;
				return false;
			}
		} catch {}
		return true;
	});
	useEffect(() => {
		return subscribe(() => {
			if (checkForUpdates()) forceUpdate();
		});
	}, [subscribe]);
	useEffect(() => {
		if (!checkForUpdates()) return;
		if (++commitCheckDepth.current > 50) {
			commitCheckDepth.current = 0;
			throw new Error("Maximum update depth exceeded. The result of getSnapshot should be cached to avoid an infinite loop.");
		}
		forceUpdate();
	}, [
		subscribe,
		value,
		getSnapshot
	]);
	return value;
};
//#endregion
export { useSyncExternalStore };
