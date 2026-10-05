"use client";
import { createContext, useContext } from "@assistant-ui/tap/react-shim";
//#region src/primitives/composer/ComposerCompactContext.tsx
const ComposerCompactContext = createContext(null);
const useComposerCompactContextOptional = () => {
	return useContext(ComposerCompactContext);
};
//#endregion
export { ComposerCompactContext, useComposerCompactContextOptional };
