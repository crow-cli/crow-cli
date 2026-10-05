"use client";
import { useModelContextSnapshot } from "../useModelContextSnapshot.js";
import { getDefaultWebMcpHost } from "./webmcp-host.js";
import { defaultWebMcpFilter, toWebMcpInputSchema } from "./convertTools.js";
import { WebMcpRegistrationResource } from "./WebMcpRegistrationResource.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useCallback, useEffect, useInsertionEffect, useRef, useState, useSyncExternalStore } from "@assistant-ui/tap/react-shim";
import { useAui } from "@assistant-ui/store";
import { useResources, useTapRoot, withKey } from "@assistant-ui/tap";
import { shallowEqual } from "@assistant-ui/store/internal";
//#region src/unstable/webmcp/useWebMcpProvider.ts
const EMPTY_NAMES = Object.freeze([]);
const EMPTY_TOOLS = Object.freeze({});
const warned = /* @__PURE__ */ new WeakSet();
const signatures = /* @__PURE__ */ new WeakMap();
const signatureOf = (tool) => {
	const cached = signatures.get(tool);
	if (cached && cached.description === tool.description) return cached.signature;
	const signature = `${tool.description ?? ""}\u0000${JSON.stringify(toWebMcpInputSchema(tool))}`;
	signatures.set(tool, {
		description: tool.description,
		signature
	});
	return signature;
};
const NO_SUBSCRIPTION = () => {};
const modelContextToolSource = {
	empty: EMPTY_TOOLS,
	read: (aui) => aui.modelContext.getModelContext().tools ?? EMPTY_TOOLS,
	subscribe: (aui, onChange) => aui.modelContext.subscribe?.(onChange) ?? NO_SUBSCRIPTION
};
const useStableNames = (names) => {
	const [cell] = useState(() => ({ names: EMPTY_NAMES }));
	const next = names.filter((name) => name !== null).sort();
	const previous = cell.names;
	if (shallowEqual(previous, next)) return previous;
	cell.names = next;
	return next;
};
const useWebMcpRegistry = (t0) => {
	const $ = c(5);
	const { host, filter, tools, getCurrentTool } = t0;
	let elements;
	if ($[0] !== filter || $[1] !== getCurrentTool || $[2] !== host || $[3] !== tools) {
		elements = [];
		for (const [name, tool] of Object.entries(tools)) try {
			if (!filter(name, tool)) continue;
			const signature = signatureOf(tool);
			elements.push(withKey(name, WebMcpRegistrationResource({
				host,
				name,
				signature,
				tool,
				getCurrentTool
			}), [
				host,
				name,
				signature,
				tool,
				getCurrentTool
			]));
		} catch (t1) {
			const error = t1;
			if (warned.has(tool)) continue;
			warned.add(tool);
			console.warn(`[assistant-ui] Skipping WebMCP registration for tool "${name}": filter or schema conversion failed.`, error);
		}
		$[0] = filter;
		$[1] = getCurrentTool;
		$[2] = host;
		$[3] = tools;
		$[4] = elements;
	} else elements = $[4];
	return useStableNames(useResources(elements));
};
/**
* Publishes the frontend tools in the model context to a WebMCP-capable
* browser, so the user's own browser agent can call them.
*
* Returns `status: "unsupported"` when the page exposes no
* `document.modelContext` (or `navigator.modelContext`), and the sorted names
* of the tools currently registered with the host.
*/
const unstable_useWebMcpProvider = (options = {}) => {
	const aui = useAui();
	const [host] = useState(getDefaultWebMcpHost);
	const filter = options.filter ?? defaultWebMcpFilter;
	const tools = useModelContextSnapshot(aui, host.available, modelContextToolSource);
	const currentToolsRef = useRef(tools);
	useInsertionEffect(() => {
		currentToolsRef.current = tools;
	}, [tools]);
	const getCurrentTool = useCallback((name) => currentToolsRef.current[name], []);
	const root = useTapRoot(function WebMcpProviderRoot() {
		return useWebMcpRegistry({
			host,
			filter,
			tools,
			getCurrentTool
		});
	});
	const registeredToolNames = useSyncExternalStore(root.subscribe, root.getValue, () => EMPTY_NAMES);
	const [published, setPublished] = useState(false);
	useEffect(() => {
		if (host.available) setPublished(true);
	}, [host]);
	return {
		status: published ? "active" : "unsupported",
		registeredToolNames
	};
};
//#endregion
export { unstable_useWebMcpProvider };
