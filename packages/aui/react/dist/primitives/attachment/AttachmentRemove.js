"use client";
import { createActionButton } from "../../utils/createActionButton.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import "@assistant-ui/tap/react-shim";
import { useAui } from "@assistant-ui/store";
//#region src/primitives/attachment/AttachmentRemove.ts
const useAttachmentRemove = () => {
	const $ = c(2);
	const aui = useAui();
	let t0;
	if ($[0] !== aui.attachment) {
		t0 = () => {
			aui.attachment.remove();
		};
		$[0] = aui.attachment;
		$[1] = t0;
	} else t0 = $[1];
	return t0;
};
const AttachmentPrimitiveRemove = createActionButton("AttachmentPrimitive.Remove", useAttachmentRemove);
//#endregion
export { AttachmentPrimitiveRemove };
