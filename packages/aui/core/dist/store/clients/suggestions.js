import { useClientLookup } from "@assistant-ui/store/client";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useMemo } from "@assistant-ui/tap/react-shim";
import { resource, withKey } from "@assistant-ui/tap";
import { shallowEqual as shallowEqual$1 } from "@assistant-ui/store/internal";
//#region src/store/clients/suggestions.ts
const useStableSuggestionsState = (next) => {
	const cell = useMemo(() => ({}), []);
	const previous = cell.state;
	const suggestions = [];
	next.suggestions.forEach((suggestion) => {
		const previousSuggestion = previous?.suggestions[suggestions.length];
		suggestions.push(previousSuggestion && shallowEqual$1(previousSuggestion, suggestion) ? previousSuggestion : suggestion);
	});
	const state = previous && shallowEqual$1(suggestions, previous.suggestions) ? previous : { suggestions };
	cell.state = state;
	return state;
};
const useSuggestionClient = (state) => {
	return { getState: () => state };
};
const SuggestionClient = resource(useSuggestionClient);
const useSuggestionsClient = (nextState) => {
	const $ = c(9);
	const state = useStableSuggestionsState(nextState);
	let t0;
	if ($[0] !== state.suggestions) {
		t0 = state.suggestions.map(_temp);
		$[0] = state.suggestions;
		$[1] = t0;
	} else t0 = $[1];
	const suggestionClients = useClientLookup(t0);
	let t1;
	if ($[2] !== state) {
		t1 = () => state;
		$[2] = state;
		$[3] = t1;
	} else t1 = $[3];
	let t2;
	if ($[4] !== suggestionClients) {
		t2 = (t3) => {
			const { index: index_0 } = t3;
			return suggestionClients.get({ index: index_0 });
		};
		$[4] = suggestionClients;
		$[5] = t2;
	} else t2 = $[5];
	let t3;
	if ($[6] !== t1 || $[7] !== t2) {
		t3 = {
			getState: t1,
			suggestion: t2
		};
		$[6] = t1;
		$[7] = t2;
		$[8] = t3;
	} else t3 = $[8];
	return t3;
};
const useStaticSuggestions = (suggestions) => {
	const $ = c(6);
	let t0;
	if ($[0] !== suggestions) {
		t0 = suggestions ?? [];
		$[0] = suggestions;
		$[1] = t0;
	} else t0 = $[1];
	let t1;
	if ($[2] !== t0) {
		t1 = t0.map(_temp2);
		$[2] = t0;
		$[3] = t1;
	} else t1 = $[3];
	let t2;
	if ($[4] !== t1) {
		t2 = { suggestions: t1 };
		$[4] = t1;
		$[5] = t2;
	} else t2 = $[5];
	return useSuggestionsClient(t2);
};
const Suggestions = resource(useStaticSuggestions);
const useThreadSuggestions = (suggestions) => {
	const $ = c(4);
	let t0;
	if ($[0] !== suggestions) {
		t0 = suggestions.map(_temp3);
		$[0] = suggestions;
		$[1] = t0;
	} else t0 = $[1];
	let t1;
	if ($[2] !== t0) {
		t1 = { suggestions: t0 };
		$[2] = t0;
		$[3] = t1;
	} else t1 = $[3];
	return useSuggestionsClient(t1);
};
const ThreadSuggestions = resource(useThreadSuggestions);
function _temp(suggestion, index) {
	return withKey(index, SuggestionClient(suggestion), [suggestion]);
}
function _temp2(s) {
	return typeof s === "string" ? {
		title: s,
		label: "",
		prompt: s
	} : {
		title: s.title,
		label: s.label,
		prompt: s.prompt
	};
}
function _temp3(s) {
	return {
		title: s.title ?? s.prompt,
		label: s.label ?? "",
		prompt: s.prompt
	};
}
//#endregion
export { Suggestions, ThreadSuggestions };
