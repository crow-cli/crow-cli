//#region src/core/tool/schema-utils.ts
const DRAFT_07_SCHEMA_IDS = /* @__PURE__ */ new Set(["http://json-schema.org/draft-07/schema", "https://json-schema.org/draft-07/schema"]);
function isStandardSchema(schema) {
	return typeof schema === "object" && schema !== null && "~standard" in schema && typeof schema["~standard"] === "object";
}
function hasToJSONSchemaMethod(schema) {
	return typeof schema === "object" && schema !== null && "toJSONSchema" in schema && typeof schema.toJSONSchema === "function";
}
function hasToJSONMethod(schema) {
	return typeof schema === "object" && schema !== null && "toJSON" in schema && typeof schema.toJSON === "function";
}
/**
* Checks that the Standard JSON Schema converter honored the target it was
* handed. That converter declares `StandardJSONSchemaV1.Options` as its input,
* so `"draft-07"` is a term it agreed to and another dialect back is a broken
* contract. No other conversion path agreed to anything.
*
* A declared `$schema` is the only place the answer shows, so a result that
* declares nothing is accepted.
*/
function assertRequestedTarget(result) {
	if (typeof result === "object" && result !== null) {
		const declared = result.$schema;
		if (typeof declared === "string" && !DRAFT_07_SCHEMA_IDS.has(declared.replace(/#$/, ""))) throw new Error(`The schema library was asked for a draft-07 JSON Schema and returned "${declared}". Upgrade the library, or pass a plain JSON Schema object instead.`);
	}
	return result;
}
/**
* Converts a schema to JSONSchema7.
* Supports:
* - StandardSchemaV1 with ~standard.jsonSchema.input() (e.g., Zod v4)
* - Objects with toJSONSchema() method
* - Objects with toJSON() method
* - Plain JSONSchema7 objects
*
* Every path that takes options is asked for draft-07. Only `~standard.jsonSchema`
* declares the option type it accepts, so only its answer is held to it; the
* duck-typed paths pass through in whatever dialect they return.
*/
function toJSONSchema(schema) {
	if (isStandardSchema(schema)) {
		const jsonSchema = schema["~standard"].jsonSchema;
		if (typeof jsonSchema === "object" && jsonSchema !== null && typeof jsonSchema.input === "function") return assertRequestedTarget(jsonSchema.input({ target: "draft-07" }));
	}
	if (hasToJSONSchemaMethod(schema)) return schema.toJSONSchema({ target: "draft-07" });
	if (hasToJSONMethod(schema)) return schema.toJSON();
	if (isStandardSchema(schema)) {
		const { vendor } = schema["~standard"];
		const helper = vendor === "zod" ? "convert it with z.toJSONSchema(schema)" : `wrap the schema with ${vendor}'s Standard JSON Schema helper`;
		throw new Error(`Could not convert the "${vendor}" schema to JSON Schema: it has no "~standard.jsonSchema" converter. Upgrade ${vendor} to a release that implements Standard JSON Schema, ${helper}, or pass a plain JSON Schema object instead.`);
	}
	return schema;
}
/**
* Returns a copy of the JSON Schema with `required` removed recursively,
* making every property optional. Array item schemas are left unchanged.
*/
function toPartialJSONSchema(schema) {
	const { required: _, ...result } = schema;
	if (result.properties) result.properties = Object.fromEntries(Object.entries(result.properties).map(([key, prop]) => {
		if (typeof prop === "object" && prop !== null && !Array.isArray(prop)) return [key, toPartialJSONSchema(prop)];
		return [key, prop];
	}));
	return result;
}
function defaultToolFilter(_name, tool) {
	return !tool.disabled && tool.type !== "backend" && (tool.type !== "frontend" || tool.execute !== void 0);
}
function toolHasUploadableParameters(tool) {
	return tool.parameters !== void 0 && !tool.unstable_backendDefault?.parameters;
}
/**
* Converts a record of tools to a record of tool definitions with JSON Schema parameters.
* By default, filters out disabled tools and backend tools.
*
* Entries are emitted in alphabetical order so the resulting request body is
* byte-identical regardless of the order in which tools were registered. This
* keeps provider prompt caches stable across renders that mount tools in
* different orders.
*/
function toToolsJSONSchema(tools, options = {}) {
	if (!tools) return {};
	const filter = options.filter ?? defaultToolFilter;
	return Object.fromEntries(Object.entries(tools).filter(([name, tool]) => filter(name, tool)).filter((entry) => toolHasUploadableParameters(entry[1])).sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0).map(([name, tool]) => [name, {
		...tool.description && { description: tool.description },
		parameters: toJSONSchema(tool.parameters),
		...tool.providerOptions && { providerOptions: tool.providerOptions }
	}]));
}
//#endregion
export { toJSONSchema, toPartialJSONSchema, toToolsJSONSchema };
