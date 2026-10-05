//#region src/utils/invoke-user-callback.ts
function invokeUserCallback(tag, name, callback, ...args) {
	if (!callback) return;
	const reportError = (error) => {
		try {
			console.error(`[${tag}] ${name} callback threw an error`, error);
		} catch {}
	};
	try {
		const result = callback(...args);
		if (result !== null && (typeof result === "object" || typeof result === "function") && "then" in result && typeof result.then === "function") return Promise.resolve(result).then(() => void 0, (error) => reportError(error));
	} catch (error) {
		reportError(error);
	}
}
//#endregion
export { invokeUserCallback };
