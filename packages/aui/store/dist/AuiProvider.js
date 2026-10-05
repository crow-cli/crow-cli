"use client";
import { AuiConfig } from "./AuiConfig.js";
import { AssistantContext, DefaultAssistantClient, getTapEffects, useAssistantContextValue } from "./utils/react-assistant-context.js";
import { DestroySignalContext } from "./utils/destroy-signal-context.js";
import { useHostDestroySignal } from "./utils/useHostDestroySignal.js";
import { isDevelopment } from "./utils/env.js";
import { useConfiguredAui } from "./useAui.js";
import { forwardRef, useImperativeHandle, useLayoutEffect } from "@assistant-ui/tap/react-shim";
import { jsx, jsxs } from "react/jsx-runtime";
//#region src/AuiProvider.tsx
const EMPTY_CONFIG = AuiConfig({});
const MountTapEffects = ({ effects }) => {
	"use no memo";
	useLayoutEffect(effects);
	return null;
};
/**
* Supplies an `AssistantClient` to the React tree.
*
* Place near the root of any subtree that uses {@link useAui} or the
* primitives built on it. Components rendered outside an `AuiProvider`
* receive a default client whose scope accessors throw on use, so
* missing-provider mistakes surface at the point of use.
*
* `config` is required and must be built with {@link AuiConfig}. At the top
* level, `config` alone creates this subtree's own client. Under a parent
* provider, `extends` is mandatory: pass `extends={aui}` to extend the parent
* client or `extends={null}` to isolate from it (enforced with a dev error).
* Configs are identity-insensitive — a fresh object per render is safe.
* A config whose scopes are all {@link Derived} keeps its scope set fixed
* at mount (dev-enforced); configs with a root scope, and empty configs,
* may grow and shrink scopes across renders. `ref` receives the resulting
* client after mount.
*
* When mounting a runtime built with one of the runtime hooks, use
* {@link AssistantRuntimeProvider} — it installs an `AuiProvider`
* internally — rather than wiring `AuiProvider` yourself.
*
* @example
* ```tsx
* function MessageScope({ index, children }) {
*   const aui = useAui();
*   const config = AuiConfig({
*     message: Derived({
*       source: "thread",
*       query: { index },
*       get: (aui) => aui.thread.message({ index }),
*     }),
*   });
*   return (
*     <AuiProvider extends={aui} config={config}>
*       {children}
*     </AuiProvider>
*   );
* }
* ```
*/
const AuiProvider = forwardRef(function AuiProvider(props, ref) {
	"use no memo";
	const { config, children } = props;
	const hasExtends = "extends" in props;
	const hasValue = "value" in props;
	const contextParent = useAssistantContextValue();
	if (isDevelopment) {
		if (hasExtends && hasValue) throw new Error("AuiProvider: pass either `extends` or `value`, not both.");
		if (hasExtends && props.extends === void 0) throw new Error("AuiProvider: `extends` must be a client or null, not undefined.");
		if (hasExtends && !config) throw new Error("AuiProvider: `extends` requires a `config`.");
		if (hasValue && config) throw new Error("AuiProvider: pass either `value` or `config`, not both.");
		if (!hasValue && !config) throw new Error("AuiProvider: a `config` is required.");
		if (!hasExtends && !hasValue && contextParent !== DefaultAssistantClient) throw new Error("A parent AuiProvider exists — pass extends={aui} to inherit it or extends={null} to isolate.");
	}
	const parent = hasExtends ? props.extends ?? DefaultAssistantClient : hasValue ? props.value ?? DefaultAssistantClient : contextParent;
	const destroySignal = useHostDestroySignal();
	const { client, effects } = useConfiguredAui(parent, config ?? EMPTY_CONFIG, destroySignal);
	useImperativeHandle(ref, () => client, [client]);
	return /* @__PURE__ */ jsx(DestroySignalContext.Provider, {
		value: destroySignal,
		children: /* @__PURE__ */ jsxs(AssistantContext.Provider, {
			value: client,
			children: [
				/* @__PURE__ */ jsx(MountTapEffects, { effects: getTapEffects(parent) }),
				effects && /* @__PURE__ */ jsx(MountTapEffects, { effects }),
				children
			]
		})
	});
});
//#endregion
export { AuiProvider };
