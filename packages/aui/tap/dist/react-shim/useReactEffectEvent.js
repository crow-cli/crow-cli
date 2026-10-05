import React, { useCallback, useInsertionEffect, useRef } from "react";
//#region src/react-shim/useReactEffectEvent.ts
const ReactRuntime = React;
function useReactEffectEventShim(callback) {
	const callbackRef = useRef(callback);
	useInsertionEffect(() => {
		callbackRef.current = callback;
	});
	return useCallback(((...args) => callbackRef.current(...args)), []);
}
const useReactEffectEvent = ReactRuntime.useEffectEvent ?? useReactEffectEventShim;
//#endregion
export { useReactEffectEvent };
