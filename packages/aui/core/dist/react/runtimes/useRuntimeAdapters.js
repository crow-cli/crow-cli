import { createContext, useContext } from "@assistant-ui/tap/react-shim";
import { useContextProvider } from "@assistant-ui/tap";
import { useShallowStable } from "@assistant-ui/store/internal";
//#region src/react/runtimes/useRuntimeAdapters.ts
const RuntimeAdaptersContext = createContext(null);
const useRuntimeAdaptersProvider = (adapters, fn) => {
	return useContextProvider(RuntimeAdaptersContext, adapters, fn);
};
const useRuntimeAdapters = () => {
	return useContext(RuntimeAdaptersContext);
};
const NO_ADAPTERS = {};
const useStableRuntimeAdapters = (adapters) => {
	const stable = useShallowStable(adapters ?? NO_ADAPTERS);
	return adapters == null ? null : stable;
};
//#endregion
export { RuntimeAdaptersContext, useRuntimeAdapters, useRuntimeAdaptersProvider, useStableRuntimeAdapters };
