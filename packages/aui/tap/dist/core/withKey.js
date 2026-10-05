//#region src/core/withKey.ts
function withKey(key, target, deps) {
	if (typeof target === "function") return (...args) => withKey(key, target(...args));
	return deps ? {
		...target,
		key,
		deps
	} : {
		...target,
		key
	};
}
//#endregion
export { withKey };
