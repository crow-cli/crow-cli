import { useEffect as useEffect$1 } from "../react-hooks/useEffect.js";
import { useRef as useRef$1 } from "../react-hooks/useRef.js";
import { useContext } from "./context.js";
import { useReducer as useReducer$1 } from "../react-hooks/useReducer.js";
import { useState as useState$1 } from "../react-hooks/useState.js";
import { useMemo as useMemo$1 } from "../react-hooks/useMemo.js";
import { useCallback as useCallback$1 } from "../react-hooks/useCallback.js";
import { useInsertionEffect as useInsertionEffect$1 } from "../react-hooks/useInsertionEffect.js";
import { useEffectEvent } from "../react-hooks/useEffectEvent.js";
import { use } from "../react-hooks/use.js";
import { useSyncExternalStore } from "../react-hooks/useSyncExternalStore.js";
import { useDebugValue } from "../react-hooks/useDebugValue.js";
import { useId } from "../react-hooks/useId.js";
import { useImperativeHandle } from "../react-hooks/useImperativeHandle.js";
import { useMemoCache } from "../react-hooks/useMemoCache.js";
import React from "@assistant-ui/tap/react-shim";
//#region src/core/react-dispatcher.ts
const tapDispatcher = {
	useState: useState$1,
	useReducer: useReducer$1,
	useRef: useRef$1,
	useMemo: useMemo$1,
	useCallback: useCallback$1,
	useEffect: useEffect$1,
	useLayoutEffect: useEffect$1,
	useInsertionEffect: useInsertionEffect$1,
	useEffectEvent,
	useContext,
	use,
	useSyncExternalStore,
	useDebugValue,
	useId,
	useImperativeHandle,
	useMemoCache
};
const ReactRuntime = React;
const internals = ReactRuntime.__CLIENT_INTERNALS_DO_NOT_USE_OR_WARN_USERS_THEY_CANNOT_UPGRADE ?? ReactRuntime.__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED;
const slot = internals == null ? null : "H" in internals ? {
	get current() {
		return internals.H;
	},
	set current(d) {
		internals.H = d;
	}
} : "ReactCurrentDispatcher" in internals ? {
	get current() {
		return internals.ReactCurrentDispatcher.current;
	},
	set current(d) {
		internals.ReactCurrentDispatcher.current = d;
	}
} : null;
/**
* Runs a resource body with tap's React dispatcher installed, so real React
* hooks called inside it (`import { useState } from "react"`) route to tap, then
* restores the previous dispatcher. If React's internal dispatcher slot can't be
* found (an unsupported React version), the body runs unchanged and `react`
* hooks inside it keep throwing React's "invalid hook call".
*/
function withReactDispatcher(render) {
	if (!slot) return render();
	const previous = slot.current;
	slot.current = tapDispatcher;
	try {
		return render();
	} finally {
		slot.current = previous;
	}
}
//#endregion
export { withReactDispatcher };
