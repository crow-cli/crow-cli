import { AssistantProviderBase } from "./AssistantProvider.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { memo } from "@assistant-ui/tap/react-shim";
import { jsx } from "react/jsx-runtime";
//#region src/react/AssistantRuntimeProvider.tsx
/**
* Mounts an `AssistantRuntime` into the React tree.
*
* Accepts the runtime returned by a runtime hook (e.g. `useLocalRuntime`,
* `useExternalStoreRuntime`, `useAssistantTransportRuntime`). Internally
* installs an {@link AuiProvider}, so descendants can use `useAui`,
* `useAuiState`, `useAuiEvent`, and the primitives without any
* additional setup.
*
* @example
* ```tsx
* function App() {
*   const runtime = useLocalRuntime(MyModelAdapter);
*
*   return (
*     <AssistantRuntimeProvider runtime={runtime}>
*       <Thread />
*     </AssistantRuntimeProvider>
*   );
* }
* ```
*/
const AssistantRuntimeProvider = memo((t0) => {
	const $ = c(5);
	const { runtime, aui, config, children } = t0;
	const t1 = aui ?? null;
	let t2;
	if ($[0] !== children || $[1] !== config || $[2] !== runtime || $[3] !== t1) {
		t2 = /* @__PURE__ */ jsx(AssistantProviderBase, {
			runtime,
			aui: t1,
			config,
			children
		});
		$[0] = children;
		$[1] = config;
		$[2] = runtime;
		$[3] = t1;
		$[4] = t2;
	} else t2 = $[4];
	return t2;
});
//#endregion
export { AssistantRuntimeProvider };
