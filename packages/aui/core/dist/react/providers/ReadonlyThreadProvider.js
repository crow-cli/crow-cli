import { ThreadRuntimeImpl } from "../../runtime/api/thread-runtime.js";
import { ReadonlyThreadRuntimeCore } from "../../runtimes/readonly/ReadonlyThreadRuntimeCore.js";
import { ThreadClient } from "../../store/runtime-clients/thread-runtime-client.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useEffect, useState } from "@assistant-ui/tap/react-shim";
import { AuiConfig, AuiProvider, Derived, useAui } from "@assistant-ui/store";
import { jsx } from "react/jsx-runtime";
//#region src/react/providers/ReadonlyThreadProvider.tsx
const READONLY_THREAD_PATH = Object.freeze({
	ref: "readonly-thread",
	threadSelector: { type: "main" }
});
const READONLY_THREAD_LIST_ITEM = Object.freeze({
	id: "readonly",
	remoteId: void 0,
	externalId: void 0,
	isMain: true,
	isRunning: false,
	status: "regular",
	title: void 0
});
const READONLY_THREAD_LIST_ITEM_BINDING = Object.freeze({
	path: READONLY_THREAD_PATH,
	getState: () => READONLY_THREAD_LIST_ITEM,
	subscribe: () => () => {}
});
const ReadonlyThreadProvider = (t0) => {
	const $ = c(14);
	const { messages, children } = t0;
	let t1;
	if ($[0] !== messages) {
		t1 = () => {
			const c = new ReadonlyThreadRuntimeCore();
			c.setMessages(messages);
			return c;
		};
		$[0] = messages;
		$[1] = t1;
	} else t1 = $[1];
	const [core] = useState(t1);
	let t2;
	let t3;
	if ($[2] !== core || $[3] !== messages) {
		t2 = () => {
			core.setMessages(messages);
		};
		t3 = [core, messages];
		$[2] = core;
		$[3] = messages;
		$[4] = t2;
		$[5] = t3;
	} else {
		t2 = $[4];
		t3 = $[5];
	}
	useEffect(t2, t3);
	let t4;
	if ($[6] !== core) {
		t4 = new ThreadRuntimeImpl({
			path: READONLY_THREAD_PATH,
			getState: () => core,
			subscribe: (callback) => core.subscribe(callback),
			outerSubscribe: (callback_0) => core.subscribe(callback_0)
		}, READONLY_THREAD_LIST_ITEM_BINDING);
		$[6] = core;
		$[7] = t4;
	} else t4 = $[7];
	const threadRuntime = t4;
	const aui = useAui();
	let t5;
	if ($[8] !== threadRuntime) {
		t5 = AuiConfig({
			thread: ThreadClient({ runtime: threadRuntime }),
			composer: Derived({
				source: "thread",
				query: {},
				get: _temp
			})
		});
		$[8] = threadRuntime;
		$[9] = t5;
	} else t5 = $[9];
	const config = t5;
	let t6;
	if ($[10] !== aui || $[11] !== children || $[12] !== config) {
		t6 = /* @__PURE__ */ jsx(AuiProvider, {
			extends: aui,
			config,
			children
		});
		$[10] = aui;
		$[11] = children;
		$[12] = config;
		$[13] = t6;
	} else t6 = $[13];
	return t6;
};
function _temp(aui_0) {
	return aui_0.thread.composer();
}
//#endregion
export { ReadonlyThreadProvider };
