import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { createContext, use } from "@assistant-ui/tap/react-shim";
import { useContextProvider } from "@assistant-ui/tap";
//#region src/utils/tap-client-stack-context.ts
/**
* Symbol used to get the client index from a ClientProxy.
*/
const SYMBOL_CLIENT_INDEX = Symbol("assistant-ui.store.clientIndex");
/**
* Get the index of a client (its position in the client stack when created).
*/
const getClientIndex = (client) => {
	return client[SYMBOL_CLIENT_INDEX];
};
const ClientStackContext = createContext([]);
/**
* Get the current client stack inside a tap resource.
*/
const useClientStack = () => {
	return use(ClientStackContext);
};
/**
* Execute a callback with a client pushed onto the stack.
* The stack is duplicated, not mutated.
*/
const useClientStackProvider = (client, callback) => {
	const $ = c(3);
	const currentStack = useClientStack();
	let t0;
	if ($[0] !== client || $[1] !== currentStack) {
		t0 = [...currentStack, client];
		$[0] = client;
		$[1] = currentStack;
		$[2] = t0;
	} else t0 = $[2];
	return useContextProvider(ClientStackContext, t0, callback);
};
//#endregion
export { SYMBOL_CLIENT_INDEX, getClientIndex, useClientStack, useClientStackProvider };
