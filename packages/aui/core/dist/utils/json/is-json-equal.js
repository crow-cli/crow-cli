import { isJSONValue, isRecord } from "./is-json.js";
//#region src/utils/json/is-json-equal.ts
const MAX_JSON_DEPTH = 100;
const isJSONValueEqualAtDepth = (a, b, currentDepth) => {
	if (a === b) return true;
	if (currentDepth > MAX_JSON_DEPTH) return false;
	if (a == null || b == null) return false;
	if (Array.isArray(a)) {
		if (!Array.isArray(b) || a.length !== b.length) return false;
		return a.every((item, index) => isJSONValueEqualAtDepth(item, b[index], currentDepth + 1));
	}
	if (Array.isArray(b)) return false;
	if (!isRecord(a) || !isRecord(b)) return false;
	const aKeys = Object.keys(a);
	const bKeys = Object.keys(b);
	if (aKeys.length !== bKeys.length) return false;
	return aKeys.every((key) => Object.hasOwn(b, key) && isJSONValueEqualAtDepth(a[key], b[key], currentDepth + 1));
};
const isJSONValueEqual = (a, b) => {
	if (!isJSONValue(a) || !isJSONValue(b)) return false;
	return isJSONValueEqualAtDepth(a, b, 0);
};
//#endregion
export { isJSONValueEqual };
