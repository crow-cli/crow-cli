import { useEffect, useMemo, useRef } from "@assistant-ui/tap/react-shim";
import { resource } from "@assistant-ui/tap";
//#region src/mcp-apps/McpAppsRemoteHost.ts
const truncateBody = (body) => body.length > 500 ? `${body.slice(0, 500)}...` : body;
const extractErrorBody = (body) => {
	const trimmed = body.trim();
	if (!trimmed) return void 0;
	try {
		const parsed = JSON.parse(trimmed);
		if (parsed && typeof parsed === "object") {
			const record = parsed;
			if (typeof record.message === "string") return record.message;
			if (typeof record.error === "string") return record.error;
			if (record.error && typeof record.error === "object") {
				const error = record.error;
				if (typeof error.message === "string") return error.message;
			}
		}
	} catch {
		return truncateBody(trimmed);
	}
	return truncateBody(trimmed);
};
const readErrorBody = async (res) => {
	try {
		return extractErrorBody(await res.text());
	} catch {
		return;
	}
};
const invalidMcpAppResource = (options) => {
	throw new Error(`Invalid MCP App host response "mcp-apps/read-resource" from "${options.url}": expected a resource with non-empty string "uri" and "html" fields`);
};
const parseMcpAppResource = (value, options) => {
	if (typeof value !== "object" || value === null || Array.isArray(value)) return invalidMcpAppResource(options);
	const resource = value;
	if (typeof resource.uri !== "string" || resource.uri.trim() === "" || typeof resource.html !== "string" || resource.html.trim() === "") return invalidMcpAppResource(options);
	return value;
};
async function postToHost(options, method, params) {
	const doFetch = options.fetch ?? fetch;
	const extraHeaders = typeof options.headers === "function" ? await options.headers() : options.headers ?? {};
	const res = await doFetch(options.url, {
		method: "POST",
		headers: {
			"content-type": "application/json",
			...extraHeaders
		},
		body: JSON.stringify({
			method,
			params
		})
	});
	if (!res.ok) {
		const status = res.statusText ? `${res.status} ${res.statusText}` : `${res.status}`;
		const body = await readErrorBody(res);
		throw new Error(`MCP App host request "${method}" to "${options.url}" failed with ${status}${body ? `: ${body}` : ""}`);
	}
	try {
		return await res.json();
	} catch (cause) {
		throw new Error(`Invalid MCP App host response "${method}" from "${options.url}": expected valid JSON`, { cause });
	}
}
/**
* Creates the default HTTP host for MCP App widgets.
*
* The host POSTs widget requests to the configured route as `{ method,
* params }`, using the method names expected by the assistant-ui MCP Apps
* guide.
*/
const useMcpAppsRemoteHost = (options) => {
	const optionsRef = useRef(options);
	useEffect(() => {
		optionsRef.current = options;
	});
	const url = options.url;
	const hostState = useMemo(() => {
		let pendingOptions = options;
		const getCurrentOptions = () => optionsRef.current.url === url ? optionsRef.current : pendingOptions;
		return {
			host: {
				loadResource: async (params) => {
					const options_0 = getCurrentOptions();
					return parseMcpAppResource(await postToHost(options_0, "mcp-apps/read-resource", params), options_0);
				},
				callTool: (params_0) => postToHost(getCurrentOptions(), "tools/call", params_0),
				readResource: (params_1) => postToHost(getCurrentOptions(), "resources/read", params_1),
				listResources: (params_2) => postToHost(getCurrentOptions(), "resources/list", params_2)
			},
			updatePendingOptions: (next) => {
				pendingOptions = next;
			}
		};
	}, [url]);
	if (optionsRef.current.url !== url) hostState.updatePendingOptions(options);
	return hostState.host;
};
const McpAppsRemoteHost = resource(useMcpAppsRemoteHost);
//#endregion
export { McpAppsRemoteHost };
