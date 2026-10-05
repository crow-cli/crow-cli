import { RuntimeAdapter } from "./RuntimeAdapter.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { memo } from "@assistant-ui/tap/react-shim";
import { AuiConfig, AuiProvider } from "@assistant-ui/store";
import { jsx, jsxs } from "react/jsx-runtime";
//#region src/react/AssistantProvider.tsx
const getRenderComponent = (runtime) => {
	return runtime._core?.RenderComponent;
};
const AssistantProviderInner = ({ runtime, aui, config, children }) => {
	"use no memo";
	const RenderComponent = getRenderComponent(runtime);
	const merged = AuiConfig({
		...config,
		threads: RuntimeAdapter(runtime)
	});
	return /* @__PURE__ */ jsxs(AuiProvider, {
		extends: aui,
		config: merged,
		children: [RenderComponent && /* @__PURE__ */ jsx(RenderComponent, {}), children]
	});
};
const AssistantProviderBase = memo((t0) => {
	const $ = c(5);
	const { runtime, aui: t1, config, children } = t0;
	const aui = t1 === void 0 ? null : t1;
	let t2;
	if ($[0] !== aui || $[1] !== children || $[2] !== config || $[3] !== runtime) {
		t2 = /* @__PURE__ */ jsx(AssistantProviderInner, {
			runtime,
			aui,
			config,
			children
		});
		$[0] = aui;
		$[1] = children;
		$[2] = config;
		$[3] = runtime;
		$[4] = t2;
	} else t2 = $[4];
	return t2;
});
//#endregion
export { AssistantProviderBase, getRenderComponent };
