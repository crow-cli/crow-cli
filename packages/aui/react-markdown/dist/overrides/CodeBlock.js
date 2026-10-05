import { useMemo } from "react";
import { Fragment, jsx, jsxs } from "react/jsx-runtime";
//#region src/overrides/CodeBlock.tsx
const DefaultCodeBlock = ({ node, components: { Pre, Code, SyntaxHighlighter, CodeHeader }, language, code }) => {
	const components = useMemo(() => ({
		Pre,
		Code
	}), [Pre, Code]);
	return /* @__PURE__ */ jsxs(Fragment, { children: [/* @__PURE__ */ jsx(CodeHeader, {
		node,
		language,
		code
	}), /* @__PURE__ */ jsx(SyntaxHighlighter, {
		node,
		components,
		language,
		code
	})] });
};
//#endregion
export { DefaultCodeBlock };
