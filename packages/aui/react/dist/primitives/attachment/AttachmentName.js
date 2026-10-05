"use client";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useAuiState } from "@assistant-ui/store";
import { Fragment, jsx } from "react/jsx-runtime";
//#region src/primitives/attachment/AttachmentName.tsx
const AttachmentPrimitiveName = () => {
	const $ = c(2);
	const name = useAuiState(_temp);
	let t0;
	if ($[0] !== name) {
		t0 = /* @__PURE__ */ jsx(Fragment, { children: name });
		$[0] = name;
		$[1] = t0;
	} else t0 = $[1];
	return t0;
};
AttachmentPrimitiveName.displayName = "AttachmentPrimitive.Name";
function _temp(s) {
	return s.attachment.name;
}
//#endregion
export { AttachmentPrimitiveName };
