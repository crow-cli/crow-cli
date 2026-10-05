"use client";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useAssistantTransportRuntime as useAssistantTransportRuntime$1, useAssistantTransportSendCommand as useAssistantTransportSendCommand$1, useAssistantTransportState as useAssistantTransportState$1 } from "@assistant-ui/core/react";
//#region src/assistant-transport.ts
const useAssistantTransportRuntime = (options) => {
	return useAssistantTransportRuntime$1(options);
};
const useAssistantTransportSendCommand = () => {
	const $ = c(2);
	const send = useAssistantTransportSendCommand$1();
	let t0;
	if ($[0] !== send) {
		t0 = (command) => {
			send(command);
		};
		$[0] = send;
		$[1] = t0;
	} else t0 = $[1];
	return t0;
};
function useAssistantTransportState(selector = (state) => state) {
	return useAssistantTransportState$1(selector);
}
//#endregion
export { useAssistantTransportRuntime, useAssistantTransportSendCommand, useAssistantTransportState };
