import { useSubscribable } from "./useSubscribable.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { resource } from "@assistant-ui/tap";
//#region src/store/runtime-clients/message-part-runtime-client.ts
const useMessagePartClient = (t0) => {
	const $ = c(17);
	const { runtime } = t0;
	const state = useSubscribable(runtime);
	let t1;
	if ($[0] !== state) {
		t1 = () => state;
		$[0] = state;
		$[1] = t1;
	} else t1 = $[1];
	let t2;
	let t3;
	let t4;
	if ($[2] !== runtime) {
		t2 = (result) => runtime.addToolResult(result);
		t3 = (payload) => runtime.resumeToolCall(payload);
		t4 = (response) => runtime.respondToToolApproval(response);
		$[2] = runtime;
		$[3] = t2;
		$[4] = t3;
		$[5] = t4;
	} else {
		t2 = $[3];
		t3 = $[4];
		t4 = $[5];
	}
	let t5;
	if ($[6] !== runtime.unstable_recordInteraction) {
		t5 = runtime.unstable_recordInteraction && { unstable_recordInteraction: (input) => runtime.unstable_recordInteraction(input) };
		$[6] = runtime.unstable_recordInteraction;
		$[7] = t5;
	} else t5 = $[7];
	let t6;
	if ($[8] !== runtime) {
		t6 = () => runtime;
		$[8] = runtime;
		$[9] = t6;
	} else t6 = $[9];
	let t7;
	if ($[10] !== t1 || $[11] !== t2 || $[12] !== t3 || $[13] !== t4 || $[14] !== t5 || $[15] !== t6) {
		t7 = {
			getState: t1,
			addToolResult: t2,
			resumeToolCall: t3,
			respondToToolApproval: t4,
			...t5,
			__internal_getRuntime: t6
		};
		$[10] = t1;
		$[11] = t2;
		$[12] = t3;
		$[13] = t4;
		$[14] = t5;
		$[15] = t6;
		$[16] = t7;
	} else t7 = $[16];
	return t7;
};
const MessagePartClient = resource(useMessagePartClient);
//#endregion
export { MessagePartClient };
