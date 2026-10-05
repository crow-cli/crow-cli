"use client";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import "@assistant-ui/tap/react-shim";
//#region src/react/runtimes/useExternalStoreSharedOptions.ts
const useExternalStoreSharedOptions = (options) => {
	const $ = c(5);
	const { isDisabled, isSendDisabled, unstable_capabilities, suggestions } = options;
	let t0;
	if ($[0] !== isDisabled || $[1] !== isSendDisabled || $[2] !== suggestions || $[3] !== unstable_capabilities) {
		t0 = {
			isDisabled,
			isSendDisabled,
			unstable_capabilities,
			suggestions
		};
		$[0] = isDisabled;
		$[1] = isSendDisabled;
		$[2] = suggestions;
		$[3] = unstable_capabilities;
		$[4] = t0;
	} else t0 = $[4];
	return t0;
};
//#endregion
export { useExternalStoreSharedOptions };
