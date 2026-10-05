"use client";
import { useEffect, useRef, useState } from "@assistant-ui/tap/react-shim";
import { useAuiState } from "@assistant-ui/store";
import { useShallowSelector } from "@assistant-ui/store/internal";
//#region src/unstable/useMessageStallDetection.ts
/**
* @deprecated Under active development and might change without notice.
*
* Detects mid-run output stalls on the current message: while the message is
* running, watches its text, reasoning, and tool-argument values plus tool-result
* availability and reports a stall once they stop changing for `thresholdMs`.
* Useful for re-surfacing a "still working" indicator during tool think-time or
* provider stalls, after the first tokens have already streamed.
*
* Must be used inside a message scope.
*/
function unstable_useMessageStallDetection(options) {
	const thresholdMs = options?.thresholdMs ?? 2e3;
	const activity = useAuiState(useShallowSelector((s) => {
		if (!(s.message.status?.type === "running")) return [false];
		const values = [true, s.message.content.length];
		for (const part of s.message.content) if (part.type === "text" || part.type === "reasoning") values.push(part.type, part.text);
		else if (part.type === "tool-call") values.push(part.type, part.argsText, part.result !== void 0);
		else values.push(part.type);
		return values;
	}));
	const running = activity[0] === true;
	const lastActivityRef = useRef(Date.now());
	const [stalled, setStalled] = useState(false);
	const [, setTick] = useState(0);
	useEffect(() => {
		if (!running) return void 0;
		lastActivityRef.current = Date.now();
	}, [running, activity]);
	useEffect(() => {
		if (!running) {
			setStalled(false);
			return;
		}
		const sinceActivity = Date.now() - lastActivityRef.current;
		if (sinceActivity >= thresholdMs) {
			setStalled(true);
			return;
		}
		setStalled(false);
		const id = setTimeout(() => setStalled(true), thresholdMs - sinceActivity);
		return () => clearTimeout(id);
	}, [
		running,
		activity,
		thresholdMs
	]);
	useEffect(() => {
		if (!stalled) return void 0;
		const id = setInterval(() => setTick((t) => t + 1), 1e3);
		return () => clearInterval(id);
	}, [stalled]);
	if (!stalled) return {
		stalled: false,
		stalledForMs: 0
	};
	return {
		stalled: true,
		stalledForMs: Math.max(0, Date.now() - lastActivityRef.current)
	};
}
//#endregion
export { unstable_useMessageStallDetection };
