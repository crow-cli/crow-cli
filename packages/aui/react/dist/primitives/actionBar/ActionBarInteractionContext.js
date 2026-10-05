"use client";
import { createContext, useContext } from "@assistant-ui/tap/react-shim";
//#region src/primitives/actionBar/ActionBarInteractionContext.ts
const ActionBarInteractionContext = createContext(null);
const useActionBarInteractionContext = () => {
	return useContext(ActionBarInteractionContext);
};
//#endregion
export { ActionBarInteractionContext, useActionBarInteractionContext };
