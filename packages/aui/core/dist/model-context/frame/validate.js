//#region src/model-context/frame/validate.ts
const isRecord = (value) => typeof value === "object" && value !== null && !Array.isArray(value);
const hasOptionalPropertyType = (value, property, type) => value[property] === void 0 || typeof value[property] === type;
const isSerializedTool = (value) => isRecord(value) && Object.hasOwn(value, "parameters") && hasOptionalPropertyType(value, "description", "string") && hasOptionalPropertyType(value, "disabled", "boolean") && hasOptionalPropertyType(value, "type", "string");
const isSerializedModelContext = (value) => {
	if (!isRecord(value)) return false;
	if (!hasOptionalPropertyType(value, "system", "string")) return false;
	if (value.tools === void 0) return true;
	if (!isRecord(value.tools)) return false;
	return Object.values(value.tools).every(isSerializedTool);
};
const isFrameMessage = (value) => {
	if (!isRecord(value) || typeof value.type !== "string") return false;
	switch (value.type) {
		case "model-context-request": return true;
		case "model-context-update": return isSerializedModelContext(value.context);
		case "tool-call": return typeof value.id === "string" && typeof value.toolName === "string" && Object.hasOwn(value, "args");
		case "tool-cancel": return typeof value.id === "string";
		case "tool-result": return typeof value.id === "string" && (value.error == null || typeof value.error === "string");
		default: return false;
	}
};
//#endregion
export { isFrameMessage };
