"use client";
import { createActionButton } from "../../utils/createActionButton.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import "@assistant-ui/tap/react-shim";
import { useAui } from "@assistant-ui/store";
//#region src/primitives/queueItem/QueueItemRemove.ts
const useQueueItemRemove = () => {
	const $ = c(2);
	const aui = useAui();
	let t0;
	if ($[0] !== aui.queueItem) {
		t0 = () => {
			aui.queueItem.remove();
		};
		$[0] = aui.queueItem;
		$[1] = t0;
	} else t0 = $[1];
	return t0;
};
/**
* A button that removes this item from the queue.
*
* @example
* ```tsx
* <QueueItemPrimitive.Remove>×</QueueItemPrimitive.Remove>
* ```
*/
const QueueItemPrimitiveRemove = createActionButton("QueueItemPrimitive.Remove", useQueueItemRemove);
//#endregion
export { QueueItemPrimitiveRemove };
