import { SuggestionByIndexProvider } from "../../providers/SuggestionByIndexProvider.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { memo, useMemo } from "@assistant-ui/tap/react-shim";
import { RenderChildrenWithAccessor, useAuiState } from "@assistant-ui/store";
import { useShallowSelector } from "@assistant-ui/store/internal";
import { jsx } from "react/jsx-runtime";
//#region src/react/primitives/thread/ThreadSuggestions.tsx
/**
* A suggestion carries no id, so its identity is its content. Repeats of the
* same content get an occurrence suffix, because React keys must be unique
* and two suggestions that render the same thing are interchangeable.
*/
const toSuggestionKeys = (suggestions) => {
	const seen = /* @__PURE__ */ new Map();
	return suggestions.map((suggestion) => {
		const content = JSON.stringify([
			suggestion.title,
			suggestion.label,
			suggestion.prompt
		]);
		const occurrence = seen.get(content) ?? 0;
		seen.set(content, occurrence + 1);
		return occurrence === 0 ? content : `${content}:${occurrence}`;
	});
};
const SuggestionComponent = (t0) => {
	const $ = c(2);
	const { components } = t0;
	const Component = components.Suggestion;
	let t1;
	if ($[0] !== Component) {
		t1 = /* @__PURE__ */ jsx(Component, {});
		$[0] = Component;
		$[1] = t1;
	} else t1 = $[1];
	return t1;
};
/**
* Renders a single suggestion at the specified index.
*/
const ThreadPrimitiveSuggestionByIndex = memo((t0) => {
	const $ = c(5);
	const { index, components } = t0;
	let t1;
	if ($[0] !== components) {
		t1 = /* @__PURE__ */ jsx(SuggestionComponent, { components });
		$[0] = components;
		$[1] = t1;
	} else t1 = $[1];
	let t2;
	if ($[2] !== index || $[3] !== t1) {
		t2 = /* @__PURE__ */ jsx(SuggestionByIndexProvider, {
			index,
			children: t1
		});
		$[2] = index;
		$[3] = t1;
		$[4] = t2;
	} else t2 = $[4];
	return t2;
}, (prev, next) => prev.index === next.index && prev.components.Suggestion === next.components.Suggestion);
ThreadPrimitiveSuggestionByIndex.displayName = "ThreadPrimitive.SuggestionByIndex";
const ThreadPrimitiveSuggestionsInner = ({ children }) => {
	const suggestionKeys = useAuiState(useShallowSelector((s) => toSuggestionKeys(s.suggestions.suggestions)));
	return useMemo(() => {
		if (suggestionKeys.length === 0) return null;
		return suggestionKeys.map((suggestionKey, index) => /* @__PURE__ */ jsx(SuggestionByIndexProvider, {
			index,
			children: /* @__PURE__ */ jsx(RenderChildrenWithAccessor, {
				getItemState: (aui) => aui.suggestions.suggestion({ index }).getState(),
				children: (getItem) => children({ get suggestion() {
					return getItem();
				} })
			})
		}, suggestionKey));
	}, [suggestionKeys, children]);
};
/**
* Renders all suggestions.
*/
const ThreadPrimitiveSuggestionsImpl = (t0) => {
	const $ = c(4);
	const { components, children } = t0;
	if (components) {
		let t1;
		if ($[0] !== components) {
			t1 = /* @__PURE__ */ jsx(ThreadPrimitiveSuggestionsInner, { children: () => /* @__PURE__ */ jsx(SuggestionComponent, { components }) });
			$[0] = components;
			$[1] = t1;
		} else t1 = $[1];
		return t1;
	}
	let t1;
	if ($[2] !== children) {
		t1 = /* @__PURE__ */ jsx(ThreadPrimitiveSuggestionsInner, { children });
		$[2] = children;
		$[3] = t1;
	} else t1 = $[3];
	return t1;
};
ThreadPrimitiveSuggestionsImpl.displayName = "ThreadPrimitive.Suggestions";
const ThreadPrimitiveSuggestions = memo(ThreadPrimitiveSuggestionsImpl, (prev, next) => {
	if (prev.children || next.children) return prev.children === next.children;
	return prev.components.Suggestion === next.components.Suggestion;
});
//#endregion
export { ThreadPrimitiveSuggestionByIndex, ThreadPrimitiveSuggestions, ThreadPrimitiveSuggestionsImpl };
