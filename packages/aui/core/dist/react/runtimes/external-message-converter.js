"use client";
import { bindExternalStoreMessage } from "../../runtime/utils/external-store-message.js";
import { convertExternalMessages as convertExternalMessages$1, createExternalMessageConversionCache as createExternalMessageConversionCache$1 } from "../../runtime/utils/external-message-conversion.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useState } from "@assistant-ui/tap/react-shim";
//#region src/react/runtimes/external-message-converter.ts
/**
* Creates a cache for plain external message conversion. Pass the same cache on every call for one message list, and a source message that has not changed since the previous call converts to the same `ThreadMessage` object.
*
* Entries are keyed by source message identity and rebuilt whenever `callback` or `metadata` is a different object than on the previous call, so keep both referentially stable.
*/
const createExternalMessageConversionCache = () => createExternalMessageConversionCache$1();
const convertExternalMessages = (messages, callback, isRunning, metadata, cache) => convertExternalMessages$1(messages, callback, isRunning, metadata, void 0, cache);
const useExternalMessageConverter = (t0) => {
	const $ = c(12);
	const { callback, messages, isRunning, joinStrategy, metadata } = t0;
	const [cache] = useState(_temp);
	let t1;
	if ($[0] !== metadata) {
		t1 = metadata ?? {};
		$[0] = metadata;
		$[1] = t1;
	} else t1 = $[1];
	let t2;
	if ($[2] !== callback || $[3] !== t1) {
		t2 = {
			metadata: t1,
			callback
		};
		$[2] = callback;
		$[3] = t1;
		$[4] = t2;
	} else t2 = $[4];
	const state = t2;
	let threadMessages;
	if ($[5] !== cache || $[6] !== isRunning || $[7] !== joinStrategy || $[8] !== messages || $[9] !== state.callback || $[10] !== state.metadata) {
		threadMessages = convertExternalMessages$1(messages, state.callback, isRunning, state.metadata, joinStrategy, cache);
		bindExternalStoreMessage(threadMessages, messages);
		$[5] = cache;
		$[6] = isRunning;
		$[7] = joinStrategy;
		$[8] = messages;
		$[9] = state.callback;
		$[10] = state.metadata;
		$[11] = threadMessages;
	} else threadMessages = $[11];
	return threadMessages;
};
function _temp() {
	return createExternalMessageConversionCache$1();
}
//#endregion
export { convertExternalMessages, createExternalMessageConversionCache, useExternalMessageConverter };
