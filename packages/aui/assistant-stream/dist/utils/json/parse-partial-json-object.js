import { fixJson } from "./fix-json.js";
import sjson from "secure-json-parse";
//#region src/utils/json/parse-partial-json-object.ts
const PARTIAL_JSON_OBJECT_META_SYMBOL = Symbol("aui.parse-partial-json-object.meta");
const getPartialJsonObjectMeta = (obj) => {
	return obj?.[PARTIAL_JSON_OBJECT_META_SYMBOL];
};
const parsePartialJsonObject = (json) => {
	if (json.length === 0) return { [PARTIAL_JSON_OBJECT_META_SYMBOL]: {
		state: "partial",
		partialPath: []
	} };
	try {
		const res = sjson.parse(json);
		if (typeof res !== "object" || res === null) throw new Error("argsText is expected to be an object");
		res[PARTIAL_JSON_OBJECT_META_SYMBOL] = {
			state: "complete",
			partialPath: []
		};
		return res;
	} catch {
		try {
			const [fixedJson, partialPath] = fixJson(json);
			const res = sjson.parse(fixedJson);
			if (typeof res !== "object" || res === null) throw new Error("argsText is expected to be an object");
			res[PARTIAL_JSON_OBJECT_META_SYMBOL] = {
				state: "partial",
				partialPath
			};
			return res;
		} catch {
			return;
		}
	}
};
const getFieldState = (parent, parentMeta, fieldPath) => {
	if (typeof parent !== "object" || parent === null) return parentMeta.state;
	if (parentMeta.state === "complete") return "complete";
	if (fieldPath.length === 0) return parentMeta.state;
	const [field, ...restPath] = fieldPath;
	if (!Object.hasOwn(parent, field)) return "partial";
	const [partialField, ...restPartialPath] = parentMeta.partialPath;
	if (field !== partialField) return "complete";
	const child = parent[field];
	return getFieldState(child, {
		state: "partial",
		partialPath: restPartialPath
	}, restPath);
};
const getPartialJsonObjectFieldState = (obj, fieldPath) => {
	const meta = getPartialJsonObjectMeta(obj);
	if (!meta) throw new Error("unable to determine object state");
	return getFieldState(obj, meta, fieldPath.map(String));
};
//#endregion
export { getPartialJsonObjectFieldState, getPartialJsonObjectMeta, parsePartialJsonObject };
