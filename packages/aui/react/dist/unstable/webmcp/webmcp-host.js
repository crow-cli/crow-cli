//#region src/unstable/webmcp/webmcp-host.ts
const isThenable = (value) => typeof value?.then === "function";
const resolveModelContext = () => {
	const context = globalThis.document?.modelContext ?? globalThis.navigator?.modelContext;
	if (!context) return void 0;
	if (typeof context.registerTool === "function") return context;
	console.warn("[assistant-ui] Ignoring a modelContext with no callable registerTool; WebMCP reports unsupported.");
};
const createHost = (context) => ({
	available: true,
	registerTool: (def, onError) => {
		const controller = new AbortController();
		const handle = context.registerTool(def, { signal: controller.signal });
		if (isThenable(handle)) handle.then(() => {}, (error) => onError?.(error));
		return () => controller.abort();
	}
});
const getDefaultWebMcpHost = () => {
	const context = resolveModelContext();
	if (!context) return {
		available: false,
		registerTool: () => () => {}
	};
	return createHost(context);
};
//#endregion
export { getDefaultWebMcpHost };
