//#region src/store/env.ts
const isDevelopment = (() => {
	try {
		return process.env.NODE_ENV === "development" || process.env.NODE_ENV === "test";
	} catch {
		return false;
	}
})();
//#endregion
export { isDevelopment };
