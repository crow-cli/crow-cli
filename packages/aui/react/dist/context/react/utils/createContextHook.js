"use client";
import { useContext } from "@assistant-ui/tap/react-shim";
//#region src/context/react/utils/createContextHook.ts
/**
* Creates a context hook with optional support.
* @param context - The React context to consume.
* @param providerName - The name of the provider for error messages.
* @returns A hook function that provides the context value.
*/
function createContextHook(context, providerName) {
	function useContextHook(options) {
		const contextValue = useContext(context);
		if (!options?.optional && !contextValue) throw new Error(`This component must be used within ${providerName}.`);
		return contextValue;
	}
	return useContextHook;
}
//#endregion
export { createContextHook };
