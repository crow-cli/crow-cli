//#region src/utils/getMessagePartKeys.ts
const keysByParts = /* @__PURE__ */ new WeakMap();
const getMessagePartKeys = (parts) => {
	const cached = keysByParts.get(parts);
	if (cached) return cached;
	const keyCounts = /* @__PURE__ */ new Map();
	const identityKeys = parts.map((part) => {
		const identity = part.type === "tool-call" ? part.toolCallId : "id" in part ? part.id : void 0;
		if (!identity) return void 0;
		const key = `${part.type}:${identity}`;
		keyCounts.set(key, (keyCounts.get(key) ?? 0) + 1);
		return key;
	});
	const keys = parts.map((part, index) => {
		const key = identityKeys[index];
		return key && keyCounts.get(key) === 1 ? key : `${part.type}@${index}`;
	});
	keysByParts.set(parts, keys);
	return keys;
};
//#endregion
export { getMessagePartKeys };
