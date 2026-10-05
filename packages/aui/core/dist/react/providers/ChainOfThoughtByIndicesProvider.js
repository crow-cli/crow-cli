import { getMessagePartKeys } from "../../utils/getMessagePartKeys.js";
import { ChainOfThoughtClient } from "../../store/clients/chain-of-thought-client.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { createContext } from "@assistant-ui/tap/react-shim";
import { AuiConfig, AuiProvider, useAui, useAuiState } from "@assistant-ui/store";
import { useShallowSelector } from "@assistant-ui/store/internal";
import { jsx } from "react/jsx-runtime";
//#region src/react/providers/ChainOfThoughtByIndicesProvider.tsx
const ChainOfThoughtPartsContext = createContext(null);
const ChainOfThoughtByIndicesProvider = (t0) => {
	const $ = c(13);
	const { startIndex, endIndex, children } = t0;
	const parts = useAuiState(_temp).slice(startIndex, endIndex + 1);
	let t1;
	if ($[0] !== endIndex || $[1] !== startIndex) {
		t1 = (s_0) => getMessagePartKeys(s_0.message.parts).slice(startIndex, endIndex + 1);
		$[0] = endIndex;
		$[1] = startIndex;
		$[2] = t1;
	} else t1 = $[2];
	const partKeys = useAuiState(useShallowSelector(t1));
	let t2;
	if ($[3] !== partKeys || $[4] !== startIndex) {
		t2 = {
			partKeys,
			startIndex
		};
		$[3] = partKeys;
		$[4] = startIndex;
		$[5] = t2;
	} else t2 = $[5];
	const partsContext = t2;
	const parentAui = useAui();
	const config = AuiConfig({ chainOfThought: ChainOfThoughtClient({
		parts,
		getMessagePart: (t3) => {
			const { index } = t3;
			if (index < 0 || index >= parts.length) throw new Error(`ChainOfThought part index ${index} is out of bounds (0..${parts.length - 1})`);
			return parentAui.message.part({ index: startIndex + index });
		}
	}) });
	let t4;
	if ($[6] !== children || $[7] !== config || $[8] !== parentAui) {
		t4 = /* @__PURE__ */ jsx(AuiProvider, {
			extends: parentAui,
			config,
			children
		});
		$[6] = children;
		$[7] = config;
		$[8] = parentAui;
		$[9] = t4;
	} else t4 = $[9];
	let t5;
	if ($[10] !== partsContext || $[11] !== t4) {
		t5 = /* @__PURE__ */ jsx(ChainOfThoughtPartsContext.Provider, {
			value: partsContext,
			children: t4
		});
		$[10] = partsContext;
		$[11] = t4;
		$[12] = t5;
	} else t5 = $[12];
	return t5;
};
function _temp(s) {
	return s.message.parts;
}
//#endregion
export { ChainOfThoughtByIndicesProvider, ChainOfThoughtPartsContext };
