import { getCurrentResourceFiber, peekResourceFiber } from "../core/helpers/execution-context.js";
import { isDevelopment } from "../core/helpers/env.js";
import { addCommit } from "../core/helpers/root.js";
import { useRef } from "./useRef.js";
//#region src/react-hooks/useEffectEvent.ts
/**
* Creates a stable function reference that always calls the most recent version of the callback.
* Similar to React's useEffectEvent hook.
*
* @param callback - The callback function to wrap
* @returns A stable function reference that always calls the latest callback
*
* @example
* ```typescript
* const handleClick = useEffectEvent((value: string) => {
*   console.log(value);
* });
* // handleClick reference is stable, but always calls the latest version
* ```
*/
function useEffectEvent(callback) {
	const fiber = getCurrentResourceFiber();
	const callbackRef = useRef(callback);
	if (callbackRef.current !== callback) addCommit(fiber, () => {
		callbackRef.current = callback;
	});
	return useRef(((...args) => {
		if (isDevelopment && peekResourceFiber()) throw new Error("useEffectEvent cannot be called during render");
		return callbackRef.current(...args);
	})).current;
}
//#endregion
export { useEffectEvent };
