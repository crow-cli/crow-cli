"use client";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useAuiState } from "@assistant-ui/store";
//#region src/primitives/thread/ThreadIf.ts
const useThreadIf = (props) => {
	const $ = c(4);
	let t0;
	if ($[0] !== props.disabled || $[1] !== props.empty || $[2] !== props.running) {
		t0 = (s) => {
			if (props.empty === true && !s.thread.isEmpty) return false;
			if (props.empty === false && s.thread.isEmpty) return false;
			if (props.running === true && !s.thread.isRunning) return false;
			if (props.running === false && s.thread.isRunning) return false;
			if (props.disabled === true && !s.thread.isDisabled) return false;
			if (props.disabled === false && s.thread.isDisabled) return false;
			return true;
		};
		$[0] = props.disabled;
		$[1] = props.empty;
		$[2] = props.running;
		$[3] = t0;
	} else t0 = $[3];
	return useAuiState(t0);
};
/**
* @deprecated Use `<AuiIf condition={(s) => s.thread...} />` instead.
*/
const ThreadPrimitiveIf = (t0) => {
	const $ = c(3);
	let children;
	let query;
	if ($[0] !== t0) {
		({children, ...query} = t0);
		$[0] = t0;
		$[1] = children;
		$[2] = query;
	} else {
		children = $[1];
		query = $[2];
	}
	return useThreadIf(query) ? children : null;
};
ThreadPrimitiveIf.displayName = "ThreadPrimitive.If";
//#endregion
export { ThreadPrimitiveIf };
