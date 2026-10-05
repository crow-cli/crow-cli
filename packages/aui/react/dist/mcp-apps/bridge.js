import "./types.js";
import { invokeUserCallback, isRecord } from "@assistant-ui/core/internal";
//#region src/mcp-apps/bridge.ts
const VALID_DISPLAY_MODES = [
	"inline",
	"fullscreen",
	"pip"
];
const DEFAULT_HOST_INFO = {
	name: "assistant-ui",
	version: "0.1"
};
const METHOD_ALIASES = {
	"ui/notifications/initialized": "notifications/initialized",
	"ui/notifications/size-changed": "notifications/size_changed",
	"ui/request-display-mode": "requestDisplayMode",
	"ui/open-link": "openLink",
	"ui/update-model-context": "updateModelContext",
	"ui/message": "sendMessage",
	"notifications/message": "notifications/log"
};
const normalizeMethod = (method) => METHOD_ALIASES[method] ?? method;
const JSONRPC_ERROR = {
	parseError: -32700,
	invalidRequest: -32600,
	methodNotFound: -32601,
	invalidParams: -32602,
	internalError: -32603
};
function isJsonRpcMessage(value) {
	if (!value || typeof value !== "object") return false;
	const v = value;
	return v.jsonrpc === "2.0" && typeof v.method === "string";
}
function isRequest(msg) {
	return "id" in msg;
}
function isNotification(msg) {
	return !("id" in msg);
}
function createMcpAppBridge(opts) {
	const { frame, handlers = {}, hostInfo = DEFAULT_HOST_INFO, hostContext = {} } = opts;
	let disposed = false;
	const post = (msg) => {
		if (disposed) return;
		frame.sendMessage(msg);
	};
	const respond = (id, payload) => {
		const res = {
			jsonrpc: "2.0",
			id,
			...payload
		};
		post(res);
	};
	const errorResponse = (id, code, message, data) => {
		respond(id, { error: {
			code,
			message,
			...data !== void 0 ? { data } : {}
		} });
	};
	const reportError = (error) => {
		if (disposed) return;
		invokeUserCallback("assistant-ui", "MCP App onError", handlers.onError?.bind(handlers), error);
	};
	const handleRequest = async (req) => {
		try {
			const params = req.params;
			switch (normalizeMethod(req.method)) {
				case "ui/initialize": {
					const requestedProtocolVersion = isRecord(params) && typeof params.protocolVersion === "string" ? params.protocolVersion : "0.1";
					respond(req.id, { result: {
						protocolVersion: requestedProtocolVersion,
						host: hostInfo,
						hostInfo,
						hostContext,
						capabilities: {
							tools: handlers.callTool ? {} : void 0,
							resources: handlers.readResource || handlers.listResources ? {} : void 0,
							ui: {
								sendMessage: !!handlers.sendMessage,
								openLink: !!handlers.openLink,
								requestDisplayMode: !!handlers.requestDisplayMode,
								updateModelContext: !!handlers.updateModelContext
							}
						},
						hostCapabilities: {
							...handlers.openLink ? { openLinks: {} } : {},
							...handlers.callTool ? { serverTools: {} } : {},
							...handlers.readResource || handlers.listResources ? { serverResources: {} } : {},
							...handlers.updateModelContext ? { updateModelContext: { text: {} } } : {},
							...handlers.sendMessage ? { message: { text: {} } } : {},
							...handlers.onLog ? { logging: {} } : {}
						}
					} });
					return;
				}
				case "tools/call": {
					if (!handlers.callTool) {
						errorResponse(req.id, JSONRPC_ERROR.methodNotFound, "tools/call is not supported by this host");
						return;
					}
					const callParams = params ?? {};
					if (typeof callParams.name !== "string") {
						errorResponse(req.id, JSONRPC_ERROR.invalidParams, "tools/call requires a string 'name'");
						return;
					}
					if (handlers.allowedTools && !handlers.allowedTools.includes(callParams.name)) {
						errorResponse(req.id, JSONRPC_ERROR.invalidParams, `tool '${callParams.name}' is not allowed for this app`);
						return;
					}
					let callArgs;
					if (callParams.arguments !== void 0) {
						if (callParams.arguments === null || typeof callParams.arguments !== "object" || Array.isArray(callParams.arguments)) {
							errorResponse(req.id, JSONRPC_ERROR.invalidParams, "tools/call 'arguments' must be an object");
							return;
						}
						callArgs = callParams.arguments;
					}
					const result = await handlers.callTool({
						name: callParams.name,
						...callArgs !== void 0 ? { arguments: callArgs } : {}
					});
					respond(req.id, { result });
					return;
				}
				case "resources/read": {
					if (!handlers.readResource) {
						errorResponse(req.id, JSONRPC_ERROR.methodNotFound, "resources/read is not supported by this host");
						return;
					}
					const readParams = params ?? {};
					if (typeof readParams.uri !== "string") {
						errorResponse(req.id, JSONRPC_ERROR.invalidParams, "resources/read requires a string 'uri'");
						return;
					}
					respond(req.id, { result: await handlers.readResource({ uri: readParams.uri }) });
					return;
				}
				case "resources/list":
					if (!handlers.listResources) {
						errorResponse(req.id, JSONRPC_ERROR.methodNotFound, "resources/list is not supported by this host");
						return;
					}
					respond(req.id, { result: await handlers.listResources(params) ?? null });
					return;
				case "openLink": {
					if (!handlers.openLink) {
						errorResponse(req.id, JSONRPC_ERROR.methodNotFound, "openLink is not supported by this host");
						return;
					}
					const linkParams = params ?? {};
					if (typeof linkParams.url !== "string") {
						errorResponse(req.id, JSONRPC_ERROR.invalidParams, "openLink requires a string 'url'");
						return;
					}
					let linkProtocol;
					try {
						linkProtocol = new URL(linkParams.url).protocol;
					} catch {
						errorResponse(req.id, JSONRPC_ERROR.invalidParams, "openLink requires a valid URL");
						return;
					}
					if (linkProtocol !== "https:" && linkProtocol !== "http:") {
						errorResponse(req.id, JSONRPC_ERROR.invalidParams, "openLink only accepts http(s) URLs");
						return;
					}
					respond(req.id, { result: await handlers.openLink({ url: linkParams.url }) });
					return;
				}
				case "sendMessage":
					if (!handlers.sendMessage) {
						errorResponse(req.id, JSONRPC_ERROR.methodNotFound, "sendMessage is not supported by this host");
						return;
					}
					respond(req.id, { result: await handlers.sendMessage(params) ?? null });
					return;
				case "updateModelContext":
					if (!handlers.updateModelContext) {
						errorResponse(req.id, JSONRPC_ERROR.methodNotFound, "updateModelContext is not supported by this host");
						return;
					}
					respond(req.id, { result: await handlers.updateModelContext(params) ?? null });
					return;
				case "requestDisplayMode": {
					if (!handlers.requestDisplayMode) {
						errorResponse(req.id, JSONRPC_ERROR.methodNotFound, "requestDisplayMode is not supported by this host");
						return;
					}
					const modeParams = params ?? {};
					if (typeof modeParams.mode !== "string" || !VALID_DISPLAY_MODES.includes(modeParams.mode)) {
						errorResponse(req.id, JSONRPC_ERROR.invalidParams, "requestDisplayMode requires a valid 'mode'");
						return;
					}
					respond(req.id, { result: await handlers.requestDisplayMode({ mode: modeParams.mode }) });
					return;
				}
				default: errorResponse(req.id, JSONRPC_ERROR.methodNotFound, `Unknown method: ${req.method}`);
			}
		} catch (err) {
			const error = err instanceof Error ? err : new Error(String(err));
			reportError(error);
			errorResponse(req.id, JSONRPC_ERROR.internalError, error.message);
		}
	};
	const handleNotification = (note) => {
		try {
			switch (normalizeMethod(note.method)) {
				case "notifications/initialized":
					handlers.onInitialized?.();
					return;
				case "notifications/size_changed": {
					const p = note.params ?? {};
					handlers.onSizeChange?.({
						...typeof p.width === "number" ? { width: p.width } : {},
						...typeof p.height === "number" ? { height: p.height } : {}
					});
					return;
				}
				case "notifications/log":
					handlers.onLog?.(note.params);
					return;
				case "notifications/request_teardown":
					handlers.onRequestTeardown?.(note.params);
					return;
				case "notifications/error": {
					const p = note.params ?? {};
					reportError(new Error(typeof p.message === "string" ? p.message : "Widget error"));
					return;
				}
				default: return;
			}
		} catch (err) {
			const error = err instanceof Error ? err : new Error(String(err));
			reportError(error);
		}
	};
	const onMessage = (event) => {
		if (disposed) return;
		if (!isJsonRpcMessage(event.data)) return;
		const msg = event.data;
		if (isRequest(msg)) handleRequest(msg);
		else if (isNotification(msg)) handleNotification(msg);
	};
	return {
		onMessage,
		dispose: () => {
			disposed = true;
		},
		notifyToolInput: (input) => {
			post({
				jsonrpc: "2.0",
				method: "notifications/tools/call/input",
				params: { input }
			});
			post({
				jsonrpc: "2.0",
				method: "ui/notifications/tool-input",
				params: isRecord(input) ? { arguments: input } : {}
			});
		},
		notifyToolResult: (result) => {
			post({
				jsonrpc: "2.0",
				method: "notifications/tools/call/result",
				params: { result }
			});
			post({
				jsonrpc: "2.0",
				method: "ui/notifications/tool-result",
				params: isRecord(result) ? result : { content: [{
					type: "text",
					text: String(result)
				}] }
			});
		},
		notifyHostContextChanged: (ctx) => {
			post({
				jsonrpc: "2.0",
				method: "notifications/host_context/changed",
				params: ctx
			});
			post({
				jsonrpc: "2.0",
				method: "ui/notifications/host-context-changed",
				params: ctx
			});
		}
	};
}
//#endregion
export { createMcpAppBridge };
