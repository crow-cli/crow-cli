//#region src/utils/json/is-json.ts
function isRecord(value) {
	return value != null && typeof value === "object" && !Array.isArray(value);
}
function isJSONValue(value, currentDepth = 0) {
	if (currentDepth > 100) return false;
	if (value === null || typeof value === "string" || typeof value === "boolean") return true;
	if (typeof value === "number") return !Number.isNaN(value) && Number.isFinite(value);
	if (Array.isArray(value)) return value.every((item) => isJSONValue(item, currentDepth + 1));
	if (isRecord(value)) return Object.entries(value).every(([key, val]) => typeof key === "string" && isJSONValue(val, currentDepth + 1));
	return false;
}
function isJSONArray(value) {
	return Array.isArray(value) && value.every((item) => isJSONValue(item));
}
function isJSONObject(value) {
	return isRecord(value) && Object.entries(value).every(([key, val]) => typeof key === "string" && isJSONValue(val));
}
//#endregion
export { isJSONArray, isJSONObject, isJSONValue, isRecord };
