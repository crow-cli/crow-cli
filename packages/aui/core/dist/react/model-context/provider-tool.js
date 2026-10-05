//#region src/react/model-context/provider-tool.ts
/**
* Marks a tool as provider-executed. The use-generative compiler converts
* `execute: providerTool(...)` into a `type: "provider"` tool entry.
*/
function providerTool(_config) {
	throw new Error("[assistant-ui] providerTool() has no runtime implementation — it marks a provider-executed tool and is stripped at build time by the use-generative compiler. Reaching it means this module was not compiled (e.g. providerTool() used outside a \"use generative\" file).");
}
//#endregion
export { providerTool };
