import { isMcpAppUri } from "@assistant-ui/core";
//#region src/mcp-apps/utils.ts
/**
* Returns MCP app metadata for a tool-call part that points at a `ui://`
* resource.
*
* Returns `undefined` when the part has no MCP app metadata or the metadata
* does not reference an assistant-ui MCP app resource.
*/
function getMcpAppFromToolPart(part) {
	const app = part.mcp?.app;
	if (!app) return void 0;
	if (!isMcpAppUri(app.resourceUri)) return void 0;
	return app;
}
//#endregion
export { getMcpAppFromToolPart };
