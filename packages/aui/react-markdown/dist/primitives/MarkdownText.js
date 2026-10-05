"use client";
import { PreOverride } from "../overrides/PreOverride.js";
import { DefaultCode, DefaultCodeBlockContent, DefaultCodeHeader, DefaultPre } from "../overrides/defaultComponents.js";
import { CodeOverride } from "../overrides/CodeOverride.js";
import { INTERNAL, useMessagePartText } from "@assistant-ui/react";
import { forwardRef, memo, useDeferredValue, useMemo, useRef } from "react";
import ReactMarkdown from "react-markdown";
import { jsx } from "react/jsx-runtime";
import { useCallbackRef } from "@radix-ui/react-use-callback-ref";
import classNames from "classnames";
//#region src/primitives/MarkdownText.tsx
const { useSmooth, useSmoothStatus, withSmoothContextProvider } = INTERNAL;
const MarkdownRenderer = memo(({ text, overrideVersion: _overrideVersion, ...options }) => /* @__PURE__ */ jsx(ReactMarkdown, {
	...options,
	children: text
}));
MarkdownRenderer.displayName = "MarkdownRenderer";
const DeferredMarkdownRenderer = ({ text, ...options }) => {
	const deferredText = useDeferredValue(text);
	return /* @__PURE__ */ jsx(MarkdownRenderer, {
		text: deferredText,
		...options
	});
};
const isPlainObject = (value) => typeof value === "object" && value !== null && !Array.isArray(value);
/**
* Compares two values structurally to `depth` levels, then by identity. One
* level covers an inline `remarkPlugins={[remarkGfm]}`; two covers an inline
* `componentsByLanguage={{ mermaid: { SyntaxHighlighter } }}`, which is the
* shape the guides teach.
*/
const isShallowEqual = (a, b, depth = 1) => {
	if (Object.is(a, b)) return true;
	if (depth <= 0) return false;
	if (Array.isArray(a) && Array.isArray(b)) {
		if (a.length !== b.length) return false;
		for (let i = 0; i < a.length; i++) if (!isShallowEqual(a[i], b[i], depth - 1)) return false;
		return true;
	}
	if (isPlainObject(a) && isPlainObject(b)) {
		const keys = Object.keys(a);
		return keys.length === Object.keys(b).length && keys.every((key) => Object.hasOwn(b, key) && isShallowEqual(a[key], b[key], depth - 1));
	}
	return false;
};
/** Keeps the identity of a value whose contents are unchanged to `depth`. */
function useStableValue(value, depth) {
	const previous = useRef(value);
	if (!isShallowEqual(value, previous.current, depth)) previous.current = value;
	return previous.current;
}
/**
* Keeps the object identity of props whose values did not change, comparing one
* array level so that an inline `remarkPlugins={[remarkGfm]}` still hits the
* renderer's memo. A plugin array mutated in place keeps the old identity and is
* not observed.
*/
function useStableProps(props) {
	const previous = useRef(props);
	const read = (source, key) => source[key];
	const keys = Object.keys(props);
	const previousKeys = Object.keys(previous.current);
	if (!(keys.length === previousKeys.length && keys.every((key) => Object.hasOwn(previous.current, key) && isShallowEqual(read(props, key), read(previous.current, key))))) previous.current = props;
	return previous.current;
}
const MarkdownTextInner = ({ components: userComponents, componentsByLanguage, smooth = true, defer = false, preprocess, ...rest }) => {
	const messagePartText = useMessagePartText();
	const { text: revealedText } = useSmooth(messagePartText, smooth);
	const text = useMemo(() => preprocess ? preprocess(revealedText) : revealedText, [preprocess, revealedText]);
	const { pre = DefaultPre, code = DefaultCode, SyntaxHighlighter = DefaultCodeBlockContent, CodeHeader = DefaultCodeHeader } = userComponents ?? {};
	const useCodeOverrideComponents = useMemo(() => {
		return {
			Pre: pre,
			Code: code,
			SyntaxHighlighter,
			CodeHeader
		};
	}, [
		pre,
		code,
		SyntaxHighlighter,
		CodeHeader
	]);
	const CodeComponent = useCallbackRef((props) => /* @__PURE__ */ jsx(CodeOverride, {
		components: useCodeOverrideComponents,
		componentsByLanguage,
		...props
	}));
	const PreComponentWithFallback = useCallbackRef((props) => /* @__PURE__ */ jsx(PreOverride, {
		fallbackPre: pre,
		...props
	}));
	const components = useStableProps(useMemo(() => {
		const { pre, code, SyntaxHighlighter, CodeHeader, ...componentsRest } = userComponents ?? {};
		return {
			...componentsRest,
			pre: PreComponentWithFallback,
			code: CodeComponent
		};
	}, [
		CodeComponent,
		PreComponentWithFallback,
		userComponents
	]));
	const overrideVersion = useStableValue(useMemo(() => ({
		components: useCodeOverrideComponents,
		componentsByLanguage
	}), [useCodeOverrideComponents, componentsByLanguage]), 3);
	const Renderer = defer ? DeferredMarkdownRenderer : MarkdownRenderer;
	const stableRest = useStableProps(rest);
	return /* @__PURE__ */ jsx(Renderer, {
		text,
		components,
		overrideVersion,
		...stableRest
	});
};
const MarkdownTextPrimitiveImpl = forwardRef(({ className, containerProps, containerComponent: Container = "div", ...rest }, forwardedRef) => {
	const status = useSmoothStatus();
	return /* @__PURE__ */ jsx(Container, {
		"data-status": status.type,
		...containerProps,
		className: classNames(className, containerProps?.className),
		ref: forwardedRef,
		children: /* @__PURE__ */ jsx(MarkdownTextInner, { ...rest })
	});
});
MarkdownTextPrimitiveImpl.displayName = "MarkdownTextPrimitive";
const MarkdownTextPrimitive = withSmoothContextProvider(MarkdownTextPrimitiveImpl);
//#endregion
export { MarkdownTextPrimitive };
