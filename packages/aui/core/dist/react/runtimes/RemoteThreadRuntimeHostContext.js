import { createContext, useContext } from "@assistant-ui/tap/react-shim";
import { useContextProvider } from "@assistant-ui/tap";
//#region src/react/runtimes/RemoteThreadRuntimeHostContext.ts
const RemoteThreadRuntimeHostContext = createContext(false);
const useRemoteThreadRuntimeHostProvider = (fn) => {
	return useContextProvider(RemoteThreadRuntimeHostContext, true, fn);
};
const useIsRemoteThreadRuntimeHosted = () => {
	return useContext(RemoteThreadRuntimeHostContext);
};
//#endregion
export { useIsRemoteThreadRuntimeHosted, useRemoteThreadRuntimeHostProvider };
