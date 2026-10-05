import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import "@assistant-ui/tap/react-shim";
import { useAui, useAuiState } from "@assistant-ui/store";
//#region src/react/primitive-hooks/useMessageBranching.ts
const useMessageBranching = () => {
	const $ = c(9);
	const aui = useAui();
	const branchNumber = useAuiState(_temp);
	const branchCount = useAuiState(_temp2);
	let t0;
	if ($[0] !== aui) {
		t0 = () => {
			aui.message.switchToBranch({ position: "previous" });
		};
		$[0] = aui;
		$[1] = t0;
	} else t0 = $[1];
	const goToPrev = t0;
	let t1;
	if ($[2] !== aui) {
		t1 = () => {
			aui.message.switchToBranch({ position: "next" });
		};
		$[2] = aui;
		$[3] = t1;
	} else t1 = $[3];
	const goToNext = t1;
	let t2;
	if ($[4] !== branchCount || $[5] !== branchNumber || $[6] !== goToNext || $[7] !== goToPrev) {
		t2 = {
			branchNumber,
			branchCount,
			goToPrev,
			goToNext
		};
		$[4] = branchCount;
		$[5] = branchNumber;
		$[6] = goToNext;
		$[7] = goToPrev;
		$[8] = t2;
	} else t2 = $[8];
	return t2;
};
function _temp(s) {
	return s.message.branchNumber;
}
function _temp2(s_0) {
	return s_0.message.branchCount;
}
//#endregion
export { useMessageBranching };
