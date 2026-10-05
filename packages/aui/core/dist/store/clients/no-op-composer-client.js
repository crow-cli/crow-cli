import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import "@assistant-ui/tap/react-shim";
import { resource } from "@assistant-ui/tap";
//#region src/store/clients/no-op-composer-client.ts
const useNoOpComposerClient = (t0) => {
	const $ = c(7);
	const { type } = t0;
	let t1;
	if ($[0] === Symbol.for("react.memo_cache_sentinel")) {
		t1 = [];
		$[0] = t1;
	} else t1 = $[0];
	let t2;
	if ($[1] === Symbol.for("react.memo_cache_sentinel")) {
		t2 = {};
		$[1] = t2;
	} else t2 = $[1];
	let t3;
	if ($[2] === Symbol.for("react.memo_cache_sentinel")) {
		t3 = [];
		$[2] = t3;
	} else t3 = $[2];
	let t4;
	if ($[3] !== type) {
		t4 = {
			isEditing: false,
			isEmpty: true,
			text: "",
			attachmentAccept: "*",
			attachments: t1,
			role: "user",
			runConfig: t2,
			canCancel: false,
			canSend: false,
			type,
			dictation: void 0,
			quote: void 0,
			queue: t3,
			submission: void 0,
			inTransit: void 0
		};
		$[3] = type;
		$[4] = t4;
	} else t4 = $[4];
	const state = t4;
	let t5;
	if ($[5] !== state) {
		t5 = {
			getState: () => state,
			setText: _temp,
			setRole: _temp2,
			setRunConfig: _temp3,
			addAttachment: _temp4,
			clearAttachments: _temp5,
			attachment: _temp6,
			reset: _temp7,
			send: _temp8,
			cancel: _temp9,
			startDictation: _temp0,
			stopDictation: _temp1,
			beginEdit: _temp10,
			setQuote: _temp11,
			queueItem: _temp12
		};
		$[5] = state;
		$[6] = t5;
	} else t5 = $[6];
	return t5;
};
const NoOpComposerClient = resource(useNoOpComposerClient);
function _temp() {
	throw new Error("Not supported");
}
function _temp2() {
	throw new Error("Not supported");
}
function _temp3() {
	throw new Error("Not supported");
}
function _temp4() {
	throw new Error("Not supported");
}
function _temp5() {
	throw new Error("Not supported");
}
function _temp6() {
	throw new Error("Not supported");
}
function _temp7() {
	throw new Error("Not supported");
}
function _temp8() {
	throw new Error("Not supported");
}
function _temp9() {
	throw new Error("Not supported");
}
function _temp0() {
	throw new Error("Not supported");
}
function _temp1() {
	throw new Error("Not supported");
}
function _temp10() {
	throw new Error("Not supported");
}
function _temp11() {
	throw new Error("Not supported");
}
function _temp12() {
	throw new Error("Not supported");
}
//#endregion
export { NoOpComposerClient };
