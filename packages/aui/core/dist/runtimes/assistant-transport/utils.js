//#region src/runtimes/assistant-transport/utils.ts
async function createRequestHeaders(headersValue) {
	const resolvedHeaders = typeof headersValue === "function" ? await headersValue() : headersValue;
	const headers = new Headers(resolvedHeaders);
	headers.set("Content-Type", "application/json");
	return headers;
}
//#endregion
export { createRequestHeaders };
