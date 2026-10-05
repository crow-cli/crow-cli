import { handleRuntimeAction } from "./handle-runtime-action.js";
import { useSubscribable } from "./useSubscribable.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { resource } from "@assistant-ui/tap";
//#region src/store/runtime-clients/attachment-runtime-client.ts
const useAttachmentRuntimeClient = (t0) => {
	const $ = c(9);
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
	if ($[2] !== runtime) {
		t2 = () => handleRuntimeAction("attachment remove", runtime.remove);
		t3 = () => runtime;
		$[2] = runtime;
		$[3] = t2;
		$[4] = t3;
	} else {
		t2 = $[3];
		t3 = $[4];
	}
	let t4;
	if ($[5] !== t1 || $[6] !== t2 || $[7] !== t3) {
		t4 = {
			getState: t1,
			remove: t2,
			__internal_getRuntime: t3
		};
		$[5] = t1;
		$[6] = t2;
		$[7] = t3;
		$[8] = t4;
	} else t4 = $[8];
	return t4;
};
const AttachmentRuntimeClient = resource(useAttachmentRuntimeClient);
//#endregion
export { AttachmentRuntimeClient };
