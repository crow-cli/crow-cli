//#region src/core/tool/ToolResponse.ts
const TOOL_RESPONSE_SYMBOL = Symbol.for("aui.tool-response");
/** Stand-in result for a tool that completed without returning a value. */
const NO_RESULT = "<no result>";
/**
* Tool result wrapper for separating UI-visible output from model-visible
* output.
*
* Return `ToolResponse` from a tool when you need to attach an artifact, mark
* the result as an error, or control the content sent back to the model.
*
* @example
* ```ts
* return new ToolResponse({
*   result: { title: "Report ready" },
*   artifact: { reportId },
*   modelContent: [{ type: "text", text: "The report is ready." }],
* });
* ```
*/
var ToolResponse = class ToolResponse {
	get [TOOL_RESPONSE_SYMBOL]() {
		return true;
	}
	artifact;
	result;
	isError;
	isPreliminary;
	modelContent;
	messages;
	constructor(options) {
		if (options.artifact !== void 0) this.artifact = options.artifact;
		const result = options.result;
		this.result = result === void 0 ? NO_RESULT : result;
		this.isError = options.isError ?? false;
		if (options.isPreliminary) this.isPreliminary = true;
		if (options.modelContent !== void 0) this.modelContent = options.modelContent;
		if (options.messages !== void 0) this.messages = options.messages;
	}
	static [Symbol.hasInstance](obj) {
		return typeof obj === "object" && obj !== null && TOOL_RESPONSE_SYMBOL in obj;
	}
	/**
	* Converts a plain tool return value into a {@link ToolResponse}.
	*
	* Existing `ToolResponse` instances are returned unchanged. `undefined`
	* becomes the string `"<no result>"` so downstream protocol chunks always
	* carry a concrete result.
	*/
	static toResponse(result) {
		if (result instanceof ToolResponse) return result;
		return new ToolResponse({ result: result === void 0 ? NO_RESULT : result });
	}
};
//#endregion
export { NO_RESULT, ToolResponse };
