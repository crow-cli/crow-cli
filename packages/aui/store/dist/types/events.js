//#region src/types/events.ts
const normalizeEventSelector = (selector) => {
	if (typeof selector === "string") return {
		scope: selector.split(".")[0],
		event: selector
	};
	return {
		scope: selector.scope,
		event: selector.event
	};
};
//#endregion
export { normalizeEventSelector };
