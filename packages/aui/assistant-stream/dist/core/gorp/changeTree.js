//#region src/core/gorp/changeTree.ts
function createChangeNode() {
	return Object.create(null);
}
const UNSAFE_PATH_SEGMENTS = /* @__PURE__ */ new Set([
	"__proto__",
	"constructor",
	"prototype"
]);
function assertSafePathSegment(segment) {
	if (UNSAFE_PATH_SEGMENTS.has(segment)) throw new Error(`Unsafe gorp path segment: ${segment}`);
}
function markChanged(node, path) {
	if (node === true || path.length === 0) return true;
	let cursor = node;
	for (let i = 0; i < path.length - 1; i++) {
		const key = path[i];
		assertSafePathSegment(key);
		const next = Object.hasOwn(cursor, key) ? cursor[key] : void 0;
		if (next === true) return node;
		if (next === void 0) cursor[key] = createChangeNode();
		cursor = cursor[key];
	}
	const leaf = path[path.length - 1];
	assertSafePathSegment(leaf);
	cursor[leaf] = true;
	return node;
}
function mergeChanged(target, source) {
	if (target === true || source === true) return true;
	for (const key of Object.keys(source)) {
		assertSafePathSegment(key);
		const sChild = source[key];
		const tChild = Object.hasOwn(target, key) ? target[key] : void 0;
		target[key] = tChild === void 0 ? cloneChangeNode(sChild) : mergeChanged(tChild, sChild);
	}
	return target;
}
function cloneChangeNode(source) {
	if (source === true) return true;
	const clone = createChangeNode();
	for (const key of Object.keys(source)) {
		assertSafePathSegment(key);
		clone[key] = cloneChangeNode(source[key]);
	}
	return clone;
}
function lookupChange(node, path) {
	for (const key of path) {
		if (node === true) return true;
		const next = Object.hasOwn(node, key) ? node[key] : void 0;
		if (next === void 0) return false;
		node = next;
	}
	return node;
}
function lookupValue(state, path) {
	let node = state;
	for (const key of path) {
		assertSafePathSegment(key);
		if (typeof node !== "object" || node === null) return void 0;
		node = Object.hasOwn(node, key) ? node[key] : void 0;
	}
	return node;
}
function diffKeys(newNode, oldNode) {
	const newKeys = typeof newNode === "object" && newNode !== null ? Object.keys(newNode) : [];
	const oldKeys = typeof oldNode === "object" && oldNode !== null ? Object.keys(oldNode) : [];
	if (oldKeys.length === 0) return newKeys;
	const newSet = new Set(newKeys);
	const deletedKeys = oldKeys.filter((k) => !newSet.has(k)).reverse();
	return [...newKeys, ...deletedKeys];
}
//#endregion
export { assertSafePathSegment, createChangeNode, diffKeys, lookupChange, lookupValue, markChanged, mergeChanged };
