//#region src/context/react/utils/createContextStoreHook.ts
/**
* Creates hooks for accessing a store within a context.
* @param contextHook - The hook to access the context.
* @param contextKey - The key of the store in the context.
* @returns An object containing the hooks: `use...` and `use...Store`.
*/
function createContextStoreHook(contextHook, contextKey) {
	function useStoreStoreHook(options) {
		const context = contextHook(options);
		if (!context) return null;
		return context[contextKey];
	}
	function useStoreHook(param) {
		let optional = false;
		let selector;
		if (typeof param === "function") selector = param;
		else if (param && typeof param === "object") {
			optional = !!param.optional;
			selector = param.selector;
		}
		const useStore = useStoreStoreHook({ optional });
		if (!useStore) return null;
		return selector ? useStore(selector) : useStore();
	}
	return {
		[contextKey]: useStoreHook,
		[`${contextKey}Store`]: useStoreStoreHook
	};
}
//#endregion
export { createContextStoreHook };
