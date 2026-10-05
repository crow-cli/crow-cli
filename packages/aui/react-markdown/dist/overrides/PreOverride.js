"use client";
import { memoCompareNodes } from "../memoization.js";
import { createContext, memo, useContext } from "react";
import { jsx } from "react/jsx-runtime";
//#region src/overrides/PreOverride.tsx
const PreContext = createContext(null);
const useIsMarkdownCodeBlock = () => {
	return useContext(PreContext) !== null;
};
const PreOverrideImpl = ({ children, fallbackPre: FallbackPre, ...rest }) => {
	if (!(rest.node?.children.some((child) => child.type === "element" && child.tagName === "code") ?? true)) return /* @__PURE__ */ jsx(FallbackPre, {
		...rest,
		children
	});
	return /* @__PURE__ */ jsx(PreContext.Provider, {
		value: rest,
		children
	});
};
const PreOverride = memo(PreOverrideImpl, (prev, next) => prev.fallbackPre === next.fallbackPre && memoCompareNodes(prev, next));
//#endregion
export { PreContext, PreOverride, useIsMarkdownCodeBlock };
