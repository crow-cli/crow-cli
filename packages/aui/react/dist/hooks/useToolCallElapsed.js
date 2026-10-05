"use client";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useEffect, useState } from "@assistant-ui/tap/react-shim";
import { useAuiState } from "@assistant-ui/store";
//#region src/hooks/useToolCallElapsed.ts
/**
* Hook that returns the elapsed wall-clock time of the current tool call in
* milliseconds, ticking once per second while the call runs.
*
* Reads `part.timing`. Returns `undefined` when the part is not a tool call,
* carries no timing, ended without a recorded completion (the duration is
* unknown), or when no message part scope is available (so kit components
* stay renderable standalone, e.g. in docs previews).
*
* @example
* ```tsx
* function ToolDuration() {
*   const elapsedMs = useToolCallElapsed();
*   if (elapsedMs === undefined) return null;
*   return <span>{(elapsedMs / 1000).toFixed(1)}s</span>;
* }
* ```
*/
const useToolCallElapsed = () => {
	const $ = c(3);
	const timing = useAuiState(_temp);
	const partRunning = useAuiState(_temp2);
	const running = timing !== void 0 && timing.completedAt === void 0 && partRunning;
	const [now, setNow] = useState(_temp3);
	let t0;
	let t1;
	if ($[0] !== running) {
		t0 = () => {
			if (!running) return;
			setNow(Date.now());
			const id = setInterval(() => setNow(Date.now()), 1e3);
			return () => clearInterval(id);
		};
		t1 = [running];
		$[0] = running;
		$[1] = t0;
		$[2] = t1;
	} else {
		t0 = $[1];
		t1 = $[2];
	}
	useEffect(t0, t1);
	if (timing === void 0) return;
	if (timing.completedAt !== void 0) return Math.max(0, timing.completedAt - timing.startedAt);
	if (!running) return;
	return Math.max(0, now - timing.startedAt);
};
function _temp(s) {
	const part = s.optional.part;
	return part?.type === "tool-call" ? part.timing : void 0;
}
function _temp2(s_0) {
	const part_0 = s_0.optional.part;
	return part_0?.type === "tool-call" && part_0.status.type === "running";
}
function _temp3() {
	return Date.now();
}
//#endregion
export { useToolCallElapsed };
