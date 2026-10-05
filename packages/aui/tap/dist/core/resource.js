//#region src/core/resource.ts
function resource(hook) {
	return (...args) => ({
		hook,
		args
	});
}
//#endregion
export { resource };
