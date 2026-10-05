//#region src/utils/json/stable-stringify-tool-args.ts
const stabilizeToolArgsValue = (value, path, keyOrderByPath) => {
	if (Array.isArray(value)) return value.map((item, idx) => stabilizeToolArgsValue(item, `${path}[${idx}]`, keyOrderByPath));
	if (value && typeof value === "object") {
		const record = value;
		const currentKeys = Object.keys(record);
		const previousOrder = keyOrderByPath.get(path) ?? [];
		const previousOrderSet = new Set(previousOrder);
		const nextOrder = [...previousOrder.filter((key) => Object.hasOwn(record, key)), ...currentKeys.filter((key) => !previousOrderSet.has(key))];
		keyOrderByPath.set(path, nextOrder);
		return Object.fromEntries(nextOrder.map((key) => [key, stabilizeToolArgsValue(record[key], `${path}.${JSON.stringify(key)}`, keyOrderByPath)]));
	}
	return value;
};
const getToolArgsKeyOrder = (keyOrderCache, cacheKey) => {
	const keyOrderByPath = keyOrderCache?.get(cacheKey) ?? /* @__PURE__ */ new Map();
	keyOrderCache?.set(cacheKey, keyOrderByPath);
	return keyOrderByPath;
};
const trackToolArgsKeyOrder = (keyOrderCache, cacheKey, args) => {
	const keyOrderByPath = getToolArgsKeyOrder(keyOrderCache, cacheKey);
	stabilizeToolArgsValue(args, "$", keyOrderByPath);
};
const stableStringifyToolArgs = (keyOrderCache, cacheKey, args) => {
	const keyOrderByPath = getToolArgsKeyOrder(keyOrderCache, cacheKey);
	const stableArgs = stabilizeToolArgsValue(args, "$", keyOrderByPath);
	return JSON.stringify(stableArgs);
};
//#endregion
export { stableStringifyToolArgs, trackToolArgsKeyOrder };
