"use client";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useEffect } from "@assistant-ui/tap/react-shim";
import { AssistantFrameHost } from "@assistant-ui/core";
//#region src/model-context/frame/useAssistantFrameHost.ts
/**
* React hook that manages the lifecycle of an AssistantFrameHost and its binding to the current AssistantRuntime.
*
* Usage example:
* ```typescript
* function MyComponent() {
*   const iframeRef = useRef<HTMLIFrameElement>(null);
*
*   useAssistantFrameHost({
*     iframeRef,
*     targetOrigin: "https://trusted-domain.com",
*   });
*
*   return <iframe ref={iframeRef} src="..." />;
* }
* ```
*/
const useAssistantFrameHost = (t0) => {
	const $ = c(5);
	const { iframeRef, targetOrigin, register } = t0;
	let t1;
	let t2;
	if ($[0] !== iframeRef || $[1] !== register || $[2] !== targetOrigin) {
		t1 = () => {
			const iframeWindow = iframeRef.current?.contentWindow;
			if (!iframeWindow) return;
			const frameHost = new AssistantFrameHost(iframeWindow, targetOrigin);
			const unsubscribe = register(frameHost);
			return () => {
				let cleanupFailed = false;
				let cleanupError;
				try {
					frameHost.dispose();
				} catch (t3) {
					const error = t3;
					cleanupFailed = true;
					cleanupError = error;
				}
				try {
					unsubscribe();
				} catch (t4) {
					const error_0 = t4;
					if (cleanupFailed) console.error("[assistant-ui] AssistantFrameHost unregistration failed.", error_0);
					else {
						cleanupFailed = true;
						cleanupError = error_0;
					}
				}
				if (cleanupFailed) throw cleanupError;
			};
		};
		t2 = [
			iframeRef,
			targetOrigin,
			register
		];
		$[0] = iframeRef;
		$[1] = register;
		$[2] = targetOrigin;
		$[3] = t1;
		$[4] = t2;
	} else {
		t1 = $[3];
		t2 = $[4];
	}
	useEffect(t1, t2);
};
//#endregion
export { useAssistantFrameHost };
