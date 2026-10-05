import { getGroupStatus } from "../../utils/getGroupStatus.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useState } from "@assistant-ui/tap/react-shim";
import { resource } from "@assistant-ui/tap";
//#region src/store/clients/chain-of-thought-client.ts
const useChainOfThoughtClient = (t0) => {
	const $ = c(11);
	const { parts, getMessagePart } = t0;
	const [collapsed, setCollapsed] = useState(true);
	let t1;
	if ($[0] !== parts) {
		t1 = getGroupStatus(parts);
		$[0] = parts;
		$[1] = t1;
	} else t1 = $[1];
	const status = t1;
	let t2;
	if ($[2] !== collapsed || $[3] !== parts || $[4] !== status) {
		t2 = {
			parts,
			collapsed,
			status
		};
		$[2] = collapsed;
		$[3] = parts;
		$[4] = status;
		$[5] = t2;
	} else t2 = $[5];
	const state = t2;
	let t3;
	if ($[6] !== state) {
		t3 = () => state;
		$[6] = state;
		$[7] = t3;
	} else t3 = $[7];
	let t4;
	if ($[8] !== getMessagePart || $[9] !== t3) {
		t4 = {
			getState: t3,
			setCollapsed,
			part: getMessagePart
		};
		$[8] = getMessagePart;
		$[9] = t3;
		$[10] = t4;
	} else t4 = $[10];
	return t4;
};
const ChainOfThoughtClient = resource(useChainOfThoughtClient);
//#endregion
export { ChainOfThoughtClient };
