"use client";
import { McpAppFrame } from "./app-frame.js";
import { getMcpAppFromToolPart } from "./utils.js";
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "@assistant-ui/tap/react-shim";
import { useAui } from "@assistant-ui/store";
import { resource, useResource } from "@assistant-ui/tap";
import { create } from "zustand";
import { isRecord } from "@assistant-ui/core/internal";
import { Fragment, jsx } from "react/jsx-runtime";
//#region src/mcp-apps/McpAppRenderer.tsx
const isSameOptions = (a, b) => {
	const aKeys = Object.keys(a).filter((key) => key !== "host");
	const bKeys = Object.keys(b).filter((key) => key !== "host");
	if (aKeys.length !== bKeys.length) return false;
	const aValues = a;
	const bValues = b;
	return aKeys.every((key) => Object.hasOwn(bValues, key) && Object.is(aValues[key], bValues[key]));
};
function getInput(part) {
	if (part.status.type === "running" && (part.argsText === "" || part.argsText === "{}")) return;
	return part.args;
}
const defaultOpenLink = ({ url }) => {
	window.open(url, "_blank", "noopener,noreferrer");
};
function extractSendMessageTexts(params) {
	if (typeof params === "string") return [params];
	if (!params || typeof params !== "object") return void 0;
	const obj = params;
	if (typeof obj["prompt"] === "string") return [obj["prompt"]];
	if (typeof obj["text"] === "string") return [obj["text"]];
	if (typeof obj["message"] === "string") return [obj["message"]];
	if (Array.isArray(obj["content"])) return obj["content"].filter((block) => isRecord(block) && block["type"] === "text" && typeof block["text"] === "string").map((block) => block.text);
}
function extractSendMessageContent(params) {
	const texts = extractSendMessageTexts(params);
	if (!texts) return { reason: "unrecognised params shape" };
	const content = texts.filter((text) => text !== "").map((text) => ({
		type: "text",
		text
	}));
	if (content.length === 0) return { reason: "no text content to append" };
	return { content };
}
function resolvePartOptions(options, part) {
	const overrides = options.forPart?.(part);
	if (!overrides) return options;
	const handlers = options.handlers && overrides.handlers ? {
		...options.handlers,
		...overrides.handlers
	} : overrides.handlers ?? options.handlers;
	return {
		...options,
		...overrides,
		...handlers === void 0 ? {} : { handlers }
	};
}
function InlineRenderer({ part, useRendererStore }) {
	const aui = useAui();
	const opts = resolvePartOptions(useRendererStore((state) => state.options), part);
	const app = getMcpAppFromToolPart(part);
	const cachedAppRef = useRef(void 0);
	useLayoutEffect(() => {
		if (app != null) cachedAppRef.current = app;
	}, [app]);
	const appForRender = app ?? cachedAppRef.current;
	const [loadedResource, setLoadedResource] = useState();
	const host = useRendererStore((state_0) => state_0.host);
	const resourceUri = appForRender?.resourceUri;
	const serverId = appForRender?.serverId;
	const callerHandlers = opts.handlers;
	useEffect(() => {
		if (resourceUri == null) return;
		let cancelled = false;
		const targetHost = host;
		const targetUri = resourceUri;
		const targetServerId = serverId;
		const loadResource = async () => {
			await Promise.resolve();
			if (cancelled || useRendererStore.getState().host !== targetHost) return;
			try {
				const res = await targetHost.loadResource({
					uri: targetUri,
					...targetServerId ? { serverId: targetServerId } : {}
				});
				if (!cancelled) setLoadedResource({
					host: targetHost,
					resourceUri: targetUri,
					...targetServerId !== void 0 ? { serverId: targetServerId } : {},
					resource: res
				});
			} catch (error) {
				if (!cancelled) setLoadedResource({
					host: targetHost,
					resourceUri: targetUri,
					...targetServerId !== void 0 ? { serverId: targetServerId } : {},
					error: error instanceof Error ? error : new Error(String(error))
				});
			}
		};
		loadResource();
		return () => {
			cancelled = true;
		};
	}, [
		host,
		resourceUri,
		serverId,
		useRendererStore
	]);
	const bridgeHandlers = useMemo(() => ({
		...callerHandlers,
		openLink: callerHandlers?.openLink ?? defaultOpenLink,
		sendMessage: callerHandlers?.sendMessage ?? ((params) => {
			const result = extractSendMessageContent(params);
			if ("reason" in result) return {
				isError: true,
				ok: false,
				reason: result.reason
			};
			aui.thread.append({ content: result.content });
			return { ok: true };
		}),
		callTool: (params_0) => useRendererStore.getState().host.callTool({
			...params_0,
			...serverId ? { serverId } : {}
		}),
		readResource: (params_1) => useRendererStore.getState().host.readResource({
			...params_1,
			...serverId ? { serverId } : {}
		}),
		listResources: (params_2) => {
			if (!serverId) return useRendererStore.getState().host.listResources(params_2);
			return useRendererStore.getState().host.listResources({
				...isRecord(params_2) ? params_2 : {},
				serverId
			});
		}
	}), [
		aui,
		callerHandlers,
		serverId,
		useRendererStore
	]);
	const loadedResourceForApp = loadedResource?.host === host && loadedResource?.resourceUri === appForRender?.resourceUri && loadedResource?.serverId === appForRender?.serverId ? loadedResource : void 0;
	const appResource = loadedResourceForApp?.resource;
	const error_0 = loadedResourceForApp?.error;
	const fallback = opts.fallback ?? null;
	if (appForRender == null) return /* @__PURE__ */ jsx(Fragment, { children: fallback });
	if (error_0 != null) {
		const errorFallback = opts.errorFallback;
		if (errorFallback === void 0) return /* @__PURE__ */ jsx(Fragment, { children: fallback });
		if (typeof errorFallback === "function") return /* @__PURE__ */ jsx(Fragment, { children: errorFallback(error_0) });
		return /* @__PURE__ */ jsx(Fragment, { children: errorFallback });
	}
	if (appResource == null) return /* @__PURE__ */ jsx(Fragment, { children: opts.loadingFallback ?? fallback });
	return /* @__PURE__ */ jsx(McpAppFrame, {
		app: appForRender,
		resource: appResource,
		input: getInput(part),
		output: part.result,
		sandbox: opts.sandbox,
		handlers: bridgeHandlers,
		hostInfo: opts.hostInfo,
		hostContext: opts.hostContext,
		maxHeight: opts.maxHeight
	});
}
/**
* Creates a tool-call renderer for MCP Apps embedded in assistant messages.
*
* Compose this into the `Tools` resource through its `mcpApp` option. When a
* tool-call part carries `mcp.app` metadata for a `ui://` resource, the
* renderer loads that resource from the configured host and displays it in a
* sandboxed frame.
*/
const useMcpAppRenderer = (options) => {
	const host = useResource(options.host);
	const [useRendererStore] = useState(() => create(() => ({
		host,
		options
	})));
	useEffect(() => {
		useRendererStore.setState((prev) => prev.host === host && isSameOptions(prev.options, options) ? prev : {
			host,
			options
		});
	}, [
		host,
		options,
		useRendererStore
	]);
	return { render: useMemo(() => {
		const Render = (props) => /* @__PURE__ */ jsx(InlineRenderer, {
			part: props,
			useRendererStore
		});
		Render.displayName = "McpAppRenderer";
		return Render;
	}, [useRendererStore]) };
};
const McpAppRenderer = resource(useMcpAppRenderer);
//#endregion
export { McpAppRenderer };
