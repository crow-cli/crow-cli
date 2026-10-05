//#region src/react/model-context/define-mcp-toolkit.ts
/**
* Defines MCP server tools as a spreadable toolkit fragment. Pass a raw
* `McpServerConfig` for always-on servers, or `{ server, disabled, tools }`
* when a server should stay configured but not expose all tools for the current
* request.
*/
function defineMcpToolkit(definition) {
	return Object.fromEntries(Object.entries(definition).map(([name, entry]) => {
		const server = "server" in entry ? entry.server : entry;
		const disabled = "server" in entry ? entry.disabled : void 0;
		const prefix = "server" in entry ? entry.prefix : void 0;
		const tools = "server" in entry ? entry.tools : void 0;
		return [name, {
			type: "mcp",
			server,
			...disabled !== void 0 && { disabled },
			...prefix !== void 0 && { prefix },
			...tools !== void 0 && { tools }
		}];
	}));
}
//#endregion
export { defineMcpToolkit };
