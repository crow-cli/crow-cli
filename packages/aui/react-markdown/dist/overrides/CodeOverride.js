import { parseLanguageClass } from "../code-fence.js";
import { memoCompareNodes } from "../memoization.js";
import { PreContext, useIsMarkdownCodeBlock } from "./PreOverride.js";
import { DefaultCodeBlockContent } from "./defaultComponents.js";
import { DefaultCodeBlock } from "./CodeBlock.js";
import { withDefaultProps } from "./withDefaults.js";
import { isValidElement, memo, useContext } from "react";
import { Fragment, jsx, jsxs } from "react/jsx-runtime";
import { useCallbackRef } from "@radix-ui/react-use-callback-ref";
//#region src/overrides/CodeOverride.tsx
function extractCode(children) {
	if (typeof children === "string") return children;
	if (Array.isArray(children)) {
		let code = "";
		for (const child of children) code += extractCode(child);
		return code;
	}
	if (isValidElement(children)) return extractCode(children.props.children);
	return "";
}
const CodeBlockOverride = ({ node, components: { Pre, Code, SyntaxHighlighter: FallbackSyntaxHighlighter, CodeHeader: FallbackCodeHeader }, componentsByLanguage = {}, children, ...codeProps }) => {
	const preProps = useContext(PreContext);
	const getPreProps = withDefaultProps(preProps);
	const WrappedPre = useCallbackRef((props) => /* @__PURE__ */ jsx(Pre, { ...getPreProps(props) }));
	const getCodeProps = withDefaultProps(codeProps);
	const WrappedCode = useCallbackRef((props) => /* @__PURE__ */ jsx(Code, { ...getCodeProps(props) }));
	const language = parseLanguageClass(codeProps.className);
	const SyntaxHighlighter = componentsByLanguage[language]?.SyntaxHighlighter ?? FallbackSyntaxHighlighter;
	const CodeHeader = componentsByLanguage[language]?.CodeHeader ?? FallbackCodeHeader;
	if (children != null && typeof children !== "string") return /* @__PURE__ */ jsxs(Fragment, { children: [/* @__PURE__ */ jsx(CodeHeader, {
		node,
		language,
		code: extractCode(children)
	}), /* @__PURE__ */ jsx(DefaultCodeBlockContent, {
		node,
		components: {
			Pre: WrappedPre,
			Code: WrappedCode
		},
		code: children
	})] });
	return /* @__PURE__ */ jsx(DefaultCodeBlock, {
		node,
		components: {
			Pre: WrappedPre,
			Code: WrappedCode,
			SyntaxHighlighter,
			CodeHeader
		},
		language,
		code: children ?? ""
	});
};
const CodeOverrideImpl = ({ node, components, componentsByLanguage, ...props }) => {
	if (!useIsMarkdownCodeBlock()) return /* @__PURE__ */ jsx(components.Code, { ...props });
	return /* @__PURE__ */ jsx(CodeBlockOverride, {
		node,
		components,
		componentsByLanguage,
		...props
	});
};
const compareComponentsByLanguage = (prev, next) => {
	if (prev === next) return true;
	if (!prev || !next) return false;
	const prevKeys = Object.keys(prev);
	if (prevKeys.length !== Object.keys(next).length) return false;
	for (const key of prevKeys) {
		if (!Object.hasOwn(next, key)) return false;
		const prevEntry = prev[key];
		const nextEntry = next[key];
		if (prevEntry === nextEntry) continue;
		if (!prevEntry || !nextEntry) return false;
		if (prevEntry.SyntaxHighlighter !== nextEntry.SyntaxHighlighter || prevEntry.CodeHeader !== nextEntry.CodeHeader) return false;
	}
	return true;
};
const CodeOverride = memo(CodeOverrideImpl, (prev, next) => {
	return prev.components === next.components && compareComponentsByLanguage(prev.componentsByLanguage, next.componentsByLanguage) && memoCompareNodes(prev, next);
});
//#endregion
export { CodeOverride, compareComponentsByLanguage };
