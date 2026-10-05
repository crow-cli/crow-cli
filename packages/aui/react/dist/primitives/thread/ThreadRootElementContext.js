"use client";
import { createContext, useContext } from "@assistant-ui/tap/react-shim";
//#region src/primitives/thread/ThreadRootElementContext.ts
const ThreadRootElementContext = createContext(void 0);
const useThreadRootElementRef = () => {
	return useContext(ThreadRootElementContext);
};
//#endregion
export { ThreadRootElementContext, useThreadRootElementRef };
