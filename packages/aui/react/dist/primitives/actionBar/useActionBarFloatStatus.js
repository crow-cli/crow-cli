"use client";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useAuiState } from "@assistant-ui/store";
//#region src/primitives/actionBar/useActionBarFloatStatus.ts
const HideAndFloatStatus = {
	Hidden: "hidden",
	Floating: "floating",
	Normal: "normal"
};
const useActionBarFloatStatus = (t0) => {
	const $ = c(5);
	const { hideWhenRunning, autohide, autohideFloat, forceVisible } = t0;
	let t1;
	if ($[0] !== autohide || $[1] !== autohideFloat || $[2] !== forceVisible || $[3] !== hideWhenRunning) {
		t1 = (s) => {
			if (hideWhenRunning && s.thread.isRunning) return HideAndFloatStatus.Hidden;
			const autohideEnabled = autohide === "always" || autohide === "not-last" && !s.message.isLast;
			const isVisibleByInteraction = forceVisible || s.message.isHovering;
			if (!autohideEnabled) return HideAndFloatStatus.Normal;
			if (!isVisibleByInteraction) return HideAndFloatStatus.Hidden;
			if (autohideFloat === "always" || autohideFloat === "single-branch" && s.message.branchCount <= 1) return HideAndFloatStatus.Floating;
			return HideAndFloatStatus.Normal;
		};
		$[0] = autohide;
		$[1] = autohideFloat;
		$[2] = forceVisible;
		$[3] = hideWhenRunning;
		$[4] = t1;
	} else t1 = $[4];
	return useAuiState(t1);
};
//#endregion
export { HideAndFloatStatus, useActionBarFloatStatus };
