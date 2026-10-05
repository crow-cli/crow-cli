//#region src/utils/notify-event-listeners.ts
const notifyEventListeners = (listeners, payloadOrFactory, errorContext) => {
	const reportError = (error) => {
		console.error(`[assistant-ui] ${errorContext} listener threw an error`, error);
	};
	for (const listener of listeners) try {
		const result = listener(typeof payloadOrFactory === "function" ? payloadOrFactory() : payloadOrFactory);
		if (result !== null && (typeof result === "object" || typeof result === "function") && "then" in result && typeof result.then === "function") Promise.resolve(result).catch(reportError);
	} catch (error) {
		reportError(error);
	}
};
//#endregion
export { notifyEventListeners };
