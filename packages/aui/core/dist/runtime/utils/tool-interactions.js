//#region src/runtime/utils/tool-interactions.ts
const TOOL_INTERACTION_LIMITS = {
	entries: 32,
	payloadLength: 16384,
	logLength: 65536
};
const MAX_DEPTH = 64;
const isPlainObject = (value) => {
	const prototype = Object.getPrototypeOf(value);
	return prototype === Object.prototype || prototype === null;
};
const isPlainJSON = (value, ancestors, depth) => {
	if (value === null) return true;
	switch (typeof value) {
		case "string":
		case "boolean": return true;
		case "number": return Number.isFinite(value);
		case "object": break;
		default: return false;
	}
	if (depth > MAX_DEPTH || ancestors.has(value)) return false;
	ancestors.add(value);
	const valid = Array.isArray(value) ? value.every((item) => isPlainJSON(item, ancestors, depth + 1)) : isPlainObject(value) && Object.values(value).every((item) => isPlainJSON(item, ancestors, depth + 1));
	ancestors.delete(value);
	return valid;
};
const isJSONObjectValue = (value) => typeof value === "object" && value !== null && !Array.isArray(value);
const isInteractionType = (value) => value === "action" || value === "human-response";
function createToolInteraction(input, occurredAt = Date.now()) {
	const { type, payload } = input;
	if (!isInteractionType(type)) throw new Error(`Unknown tool interaction type: ${String(type)}`);
	if (!isPlainJSON(payload, /* @__PURE__ */ new Set(), 0)) throw new Error("A tool interaction payload must be plain JSON.");
	if (type === "action" && !isJSONObjectValue(payload)) throw new Error("An action interaction payload must be a JSON object.");
	const serialized = JSON.stringify(payload);
	if (serialized.length > TOOL_INTERACTION_LIMITS.payloadLength) throw new Error(`A tool interaction payload is limited to ${TOOL_INTERACTION_LIMITS.payloadLength} characters of JSON.`);
	return {
		type,
		occurredAt,
		payload: JSON.parse(serialized)
	};
}
function appendToolInteraction(log, interaction) {
	const entries = [...log?.entries ?? [], interaction];
	let omitted = log?.omitted ?? 0;
	while (entries.length > 1 && (entries.length > TOOL_INTERACTION_LIMITS.entries || JSON.stringify(entries).length > TOOL_INTERACTION_LIMITS.logLength)) {
		entries.shift();
		omitted += 1;
	}
	return omitted > 0 ? {
		entries,
		omitted
	} : { entries };
}
const readInteraction = (value) => {
	if (!isJSONObjectValue(value)) return void 0;
	const { type, occurredAt, payload } = value;
	if (!isInteractionType(type)) return void 0;
	if (typeof occurredAt !== "number" || !Number.isFinite(occurredAt)) return;
	if (!isPlainJSON(payload, /* @__PURE__ */ new Set(), 0)) return void 0;
	if (type === "action") return isJSONObjectValue(payload) ? {
		type,
		occurredAt,
		payload
	} : void 0;
	return {
		type,
		occurredAt,
		payload
	};
};
function readToolInteractionLog(value) {
	if (!isJSONObjectValue(value)) return void 0;
	const { entries, omitted } = value;
	const readable = Array.isArray(entries) ? entries.flatMap((entry) => {
		const interaction = readInteraction(entry);
		return interaction ? [interaction] : [];
	}) : [];
	let omittedEntries = typeof omitted === "number" && Number.isInteger(omitted) && omitted > 0 ? omitted : 0;
	while (readable.length > 1 && (readable.length > TOOL_INTERACTION_LIMITS.entries || JSON.stringify(readable).length > TOOL_INTERACTION_LIMITS.logLength)) {
		readable.shift();
		omittedEntries += 1;
	}
	if (readable.length === 0 && omittedEntries === 0) return void 0;
	return omittedEntries > 0 ? {
		entries: readable,
		omitted: omittedEntries
	} : { entries: readable };
}
//#endregion
export { TOOL_INTERACTION_LIMITS, appendToolInteraction, createToolInteraction, readToolInteractionLog };
