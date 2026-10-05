import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import "@assistant-ui/tap/react-shim";
import { AuiConfig, AuiProvider, useAui } from "@assistant-ui/store";
import { resource } from "@assistant-ui/tap";
import { jsx } from "react/jsx-runtime";
//#region src/react/providers/TextMessagePartProvider.tsx
const useTextMessagePartClient = (t0) => {
	const $ = c(7);
	const { text, isRunning } = t0;
	let t1;
	if ($[0] !== isRunning) {
		t1 = isRunning ? { type: "running" } : { type: "complete" };
		$[0] = isRunning;
		$[1] = t1;
	} else t1 = $[1];
	let t2;
	if ($[2] !== t1 || $[3] !== text) {
		t2 = {
			type: "text",
			text,
			status: t1
		};
		$[2] = t1;
		$[3] = text;
		$[4] = t2;
	} else t2 = $[4];
	const state = t2;
	let t3;
	if ($[5] !== state) {
		t3 = {
			getState: () => state,
			addToolResult: _temp,
			resumeToolCall: _temp2,
			respondToToolApproval: _temp3,
			unstable_recordInteraction: _temp4
		};
		$[5] = state;
		$[6] = t3;
	} else t3 = $[6];
	return t3;
};
const TextMessagePartClient = resource(useTextMessagePartClient);
const TextMessagePartProvider = (t0) => {
	const $ = c(7);
	const { text, isRunning: t1, children } = t0;
	const isRunning = t1 === void 0 ? false : t1;
	const aui = useAui();
	let t2;
	if ($[0] !== isRunning || $[1] !== text) {
		t2 = AuiConfig({ part: TextMessagePartClient({
			text,
			isRunning
		}) });
		$[0] = isRunning;
		$[1] = text;
		$[2] = t2;
	} else t2 = $[2];
	const config = t2;
	let t3;
	if ($[3] !== aui || $[4] !== children || $[5] !== config) {
		t3 = /* @__PURE__ */ jsx(AuiProvider, {
			extends: aui,
			config,
			children
		});
		$[3] = aui;
		$[4] = children;
		$[5] = config;
		$[6] = t3;
	} else t3 = $[6];
	return t3;
};
function _temp() {
	throw new Error("Not supported");
}
function _temp2() {
	throw new Error("Not supported");
}
function _temp3() {
	throw new Error("Not supported");
}
async function _temp4() {
	throw new Error("Not supported");
}
//#endregion
export { TextMessagePartProvider };
