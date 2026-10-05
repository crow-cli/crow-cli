import { getCurrentResourceFiber, peekResourceFiber } from "../../core/helpers/execution-context.js";
import { isDevelopment } from "../../core/helpers/env.js";
import { useRef, useState } from "@assistant-ui/tap/react-shim";
//#region src/hooks/utils/useDevStrictMode.ts
const getTapDevMode = () => {
	const currentResourceFiber = getCurrentResourceFiber();
	if (currentResourceFiber.devStrictMode) return currentResourceFiber.isFirstRender ? "child" : "root";
	return null;
};
const child = () => "child";
const notDevMode = () => null;
const useDevStrictModeReact = () => {
	if (!isDevelopment) return notDevMode;
	const count = useRef(0);
	useState(() => count.current++);
	if (count.current !== 2) return notDevMode;
	return child;
};
const useDevStrictMode = () => {
	return peekResourceFiber() ? getTapDevMode : useDevStrictModeReact();
};
//#endregion
export { useDevStrictMode };
