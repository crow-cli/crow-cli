import { createContext, use } from "@assistant-ui/tap/react-shim";
import { useContextProvider } from "@assistant-ui/tap";
//#region src/utils/destroy-signal-context.ts
const DestroySignalContext = createContext(void 0);
/**
* Scopes a subtree to the permanent teardown of whatever owns it. The signal
* aborts when the owner is destroyed for good, never when a resource soft
* unmounts and may come back, so a consumer may release work on it without
* losing state a later reveal still needs. A caller with no owner of its own
* passes `undefined` and the enclosing owner keeps standing.
*/
const useDestroySignalProvider = (destroySignal, fn) => {
	const inherited = use(DestroySignalContext);
	return useContextProvider(DestroySignalContext, destroySignal ?? inherited, fn);
};
/**
* Returns the permanent teardown signal of the owner the caller runs under.
* A caller outside any owned subtree resolves none, which retains its
* resources rather than releasing them early.
*/
const useAssistantClientDestroySignal = () => use(DestroySignalContext);
//#endregion
export { DestroySignalContext, useAssistantClientDestroySignal, useDestroySignalProvider };
