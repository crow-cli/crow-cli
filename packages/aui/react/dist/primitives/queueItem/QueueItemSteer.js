"use client";
import { createActionButton } from "../../utils/createActionButton.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import "@assistant-ui/tap/react-shim";
import { useAui } from "@assistant-ui/store";
//#region src/primitives/queueItem/QueueItemSteer.ts
const useQueueItemSteer = () => {
	const $ = c(2);
	const aui = useAui();
	let t0;
	if ($[0] !== aui.queueItem) {
		t0 = () => {
			aui.queueItem.steer();
		};
		$[0] = aui.queueItem;
		$[1] = t0;
	} else t0 = $[1];
	return t0;
};
/**
* A button that steers the current run to process this queue item immediately.
*
* @example
* ```tsx
* <QueueItemPrimitive.Steer>Run Now</QueueItemPrimitive.Steer>
* ```
*/
const QueueItemPrimitiveSteer = createActionButton("QueueItemPrimitive.Steer", useQueueItemSteer);
//#endregion
export { QueueItemPrimitiveSteer };
