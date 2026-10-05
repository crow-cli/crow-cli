"use client";
import { createActionButton } from "../../utils/createActionButton.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useComposerAddAttachment } from "@assistant-ui/core/react";
import "@assistant-ui/tap/react-shim";
import { useAui } from "@assistant-ui/store";
//#region src/primitives/composer/ComposerAddAttachment.ts
const useComposerAddAttachment$1 = (t0) => {
	const $ = c(6);
	let t1;
	if ($[0] !== t0) {
		t1 = t0 === void 0 ? {} : t0;
		$[0] = t0;
		$[1] = t1;
	} else t1 = $[1];
	const { multiple: t2 } = t1;
	const multiple = t2 === void 0 ? true : t2;
	const { disabled, addAttachment } = useComposerAddAttachment();
	const aui = useAui();
	let t3;
	if ($[2] !== addAttachment || $[3] !== aui.composer || $[4] !== multiple) {
		t3 = () => {
			const input = document.createElement("input");
			input.type = "file";
			input.multiple = multiple;
			input.hidden = true;
			const attachmentAccept = aui.composer.getState().attachmentAccept;
			if (attachmentAccept !== "*") input.accept = attachmentAccept;
			document.body.appendChild(input);
			input.onchange = async (e) => {
				const fileList = e.target.files;
				if (!fileList) return;
				const attachmentPromises = Array.from(fileList, async (file) => {
					try {
						await addAttachment(file);
					} catch {}
				});
				document.body.removeChild(input);
				await Promise.all(attachmentPromises);
			};
			input.oncancel = () => {
				if (!input.files || input.files.length === 0) document.body.removeChild(input);
			};
			input.click();
		};
		$[2] = addAttachment;
		$[3] = aui.composer;
		$[4] = multiple;
		$[5] = t3;
	} else t3 = $[5];
	const callback = t3;
	if (disabled) return null;
	return callback;
};
const ComposerPrimitiveAddAttachment = createActionButton("ComposerPrimitive.AddAttachment", useComposerAddAttachment$1, ["multiple"]);
//#endregion
export { ComposerPrimitiveAddAttachment };
