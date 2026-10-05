import { detectTrigger } from "./detectTrigger.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useState } from "@assistant-ui/tap/react-shim";
import { resource } from "@assistant-ui/tap";
//#region src/primitives/composer/trigger/triggerDetectionResource.ts
/** Tracks cursor position and derives the active trigger + query from composer text. */
const useTriggerDetectionResource = (t0) => {
	const $ = c(8);
	const { text, triggerChar, matcher } = t0;
	const [cursorPosition, setCursorPosition] = useState(text.length);
	const pos = Math.min(cursorPosition, text.length);
	let t1;
	if ($[0] !== matcher || $[1] !== pos || $[2] !== text || $[3] !== triggerChar) {
		t1 = detectTrigger(text, triggerChar, pos, matcher);
		$[0] = matcher;
		$[1] = pos;
		$[2] = text;
		$[3] = triggerChar;
		$[4] = t1;
	} else t1 = $[4];
	const trigger = t1;
	const query = trigger?.query ?? "";
	let t2;
	if ($[5] !== query || $[6] !== trigger) {
		t2 = {
			trigger,
			query,
			setCursorPosition
		};
		$[5] = query;
		$[6] = trigger;
		$[7] = t2;
	} else t2 = $[7];
	return t2;
};
const TriggerDetectionResource = resource(useTriggerDetectionResource);
//#endregion
export { TriggerDetectionResource };
