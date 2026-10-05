"use client";
import { ThreadPrimitiveViewportProvider } from "../context/providers/ThreadViewportProvider.js";
import { DevToolsProviderApi } from "../devtools/DevToolsHooks.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { AssistantProviderBase } from "@assistant-ui/core/react";
import { memo, useEffect } from "@assistant-ui/tap/react-shim";
import { useAui } from "@assistant-ui/store";
import { jsx, jsxs } from "react/jsx-runtime";
//#region src/legacy-runtime/AssistantRuntimeProvider.tsx
const DevToolsRegistration = () => {
	const $ = c(3);
	const aui = useAui();
	let t0;
	let t1;
	if ($[0] !== aui) {
		t0 = () => {
			if (typeof process === "undefined" || process.env.NODE_ENV === "production") return;
			return DevToolsProviderApi.register(aui);
		};
		t1 = [aui];
		$[0] = aui;
		$[1] = t0;
		$[2] = t1;
	} else {
		t0 = $[1];
		t1 = $[2];
	}
	useEffect(t0, t1);
	return null;
};
const AssistantRuntimeProviderImpl = (t0) => {
	const $ = c(8);
	const { children, aui, config, runtime } = t0;
	const t1 = aui ?? null;
	let t2;
	if ($[0] === Symbol.for("react.memo_cache_sentinel")) {
		t2 = /* @__PURE__ */ jsx(DevToolsRegistration, {});
		$[0] = t2;
	} else t2 = $[0];
	let t3;
	if ($[1] !== children) {
		t3 = /* @__PURE__ */ jsx(ThreadPrimitiveViewportProvider, { children });
		$[1] = children;
		$[2] = t3;
	} else t3 = $[2];
	let t4;
	if ($[3] !== config || $[4] !== runtime || $[5] !== t1 || $[6] !== t3) {
		t4 = /* @__PURE__ */ jsxs(AssistantProviderBase, {
			runtime,
			aui: t1,
			config,
			children: [t2, t3]
		});
		$[3] = config;
		$[4] = runtime;
		$[5] = t1;
		$[6] = t3;
		$[7] = t4;
	} else t4 = $[7];
	return t4;
};
const AssistantRuntimeProvider = memo(AssistantRuntimeProviderImpl);
//#endregion
export { AssistantRuntimeProvider, AssistantRuntimeProviderImpl };
