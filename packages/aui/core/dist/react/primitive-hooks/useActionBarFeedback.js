import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import "@assistant-ui/tap/react-shim";
import { useAui, useAuiState } from "@assistant-ui/store";
//#region src/react/primitive-hooks/useActionBarFeedback.ts
const useActionBarFeedbackPositive = () => {
	const $ = c(5);
	const aui = useAui();
	const isSubmitted = useAuiState(_temp);
	let t0;
	if ($[0] !== aui) {
		t0 = () => {
			aui.message.submitFeedback({ type: "positive" });
		};
		$[0] = aui;
		$[1] = t0;
	} else t0 = $[1];
	const submit = t0;
	let t1;
	if ($[2] !== isSubmitted || $[3] !== submit) {
		t1 = {
			submit,
			isSubmitted
		};
		$[2] = isSubmitted;
		$[3] = submit;
		$[4] = t1;
	} else t1 = $[4];
	return t1;
};
const useActionBarFeedbackNegative = () => {
	const $ = c(5);
	const aui = useAui();
	const isSubmitted = useAuiState(_temp2);
	let t0;
	if ($[0] !== aui) {
		t0 = () => {
			aui.message.submitFeedback({ type: "negative" });
		};
		$[0] = aui;
		$[1] = t0;
	} else t0 = $[1];
	const submit = t0;
	let t1;
	if ($[2] !== isSubmitted || $[3] !== submit) {
		t1 = {
			submit,
			isSubmitted
		};
		$[2] = isSubmitted;
		$[3] = submit;
		$[4] = t1;
	} else t1 = $[4];
	return t1;
};
function _temp(s) {
	return s.message.metadata.submittedFeedback?.type === "positive";
}
function _temp2(s) {
	return s.message.metadata.submittedFeedback?.type === "negative";
}
//#endregion
export { useActionBarFeedbackNegative, useActionBarFeedbackPositive };
