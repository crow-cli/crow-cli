"use client";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { AuiConfig, AuiProvider, useAui } from "@assistant-ui/store";
import { jsx } from "react/jsx-runtime";
import { ThreadMessageClient } from "@assistant-ui/core/store";
//#region src/context/providers/MessageProvider.tsx
const MessageProvider = (t0) => {
	const $ = c(4);
	const { children, ...props } = t0;
	const aui = useAui();
	const config = AuiConfig({ message: ThreadMessageClient(props) });
	let t1;
	if ($[0] !== aui || $[1] !== children || $[2] !== config) {
		t1 = /* @__PURE__ */ jsx(AuiProvider, {
			extends: aui,
			config,
			children
		});
		$[0] = aui;
		$[1] = children;
		$[2] = config;
		$[3] = t1;
	} else t1 = $[3];
	return t1;
};
//#endregion
export { MessageProvider };
