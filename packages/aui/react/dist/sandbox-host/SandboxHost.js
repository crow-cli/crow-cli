"use client";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useEffect, useLayoutEffect, useRef, useState } from "@assistant-ui/tap/react-shim";
import { invokeUserCallback } from "@assistant-ui/core/internal";
import { jsx } from "react/jsx-runtime";
import { SafeContentFrame, isShimLoadError } from "safe-content-frame";
//#region src/sandbox-host/SandboxHost.tsx
const DEFAULT_PRODUCT = "assistant-ui-sandbox";
const DEFAULT_MAX_HEIGHT = 800;
const LOAD_TIMEOUT_MS = 1e4;
function isSandboxFrameMessage(event, frame) {
	return event.source === frame.iframe.contentWindow && event.origin === frame.origin;
}
function SandboxHost(t0) {
	const $ = c(21);
	const { content, contentKey, sandbox, maxHeight: t1, createBridge, onError, containerProps } = t0;
	const maxHeight = t1 === void 0 ? DEFAULT_MAX_HEIGHT : t1;
	const containerRef = useRef(null);
	const [contentHeight, setContentHeight] = useState(void 0);
	let t2;
	if ($[0] !== content || $[1] !== createBridge || $[2] !== onError || $[3] !== sandbox) {
		t2 = {
			content,
			sandbox,
			createBridge,
			onError
		};
		$[0] = content;
		$[1] = createBridge;
		$[2] = onError;
		$[3] = sandbox;
		$[4] = t2;
	} else t2 = $[4];
	const liveRef = useRef(t2);
	let t3;
	let t4;
	if ($[5] !== content || $[6] !== createBridge || $[7] !== onError || $[8] !== sandbox) {
		t3 = () => {
			liveRef.current = {
				content,
				sandbox,
				createBridge,
				onError
			};
		};
		t4 = [
			content,
			sandbox,
			createBridge,
			onError
		];
		$[5] = content;
		$[6] = createBridge;
		$[7] = onError;
		$[8] = sandbox;
		$[9] = t3;
		$[10] = t4;
	} else {
		t3 = $[9];
		t4 = $[10];
	}
	useLayoutEffect(t3, t4);
	let t5;
	if ($[11] === Symbol.for("react.memo_cache_sentinel")) {
		t5 = () => {
			const container = containerRef.current;
			if (!container) return;
			let cancelled = false;
			let frame = null;
			let bridge = null;
			let onMessage = null;
			const { content: liveContent, sandbox: sb } = liveRef.current;
			const reportError = (err) => {
				const error = err instanceof Error ? err : new Error(String(err));
				invokeUserCallback("assistant-ui", "SandboxHost onError", liveRef.current.onError?.bind(liveRef.current), error);
			};
			const scf = new SafeContentFrame(sb?.product ?? DEFAULT_PRODUCT, {
				...sb?.sandbox !== void 0 && { sandbox: sb.sandbox },
				...sb?.useShadowDom !== void 0 && { useShadowDom: sb.useShadowDom },
				...sb?.enableBrowserCaching !== void 0 && { enableBrowserCaching: sb.enableBrowserCaching },
				...sb?.salt !== void 0 && { salt: sb.salt }
			});
			const renderOpts = sb?.unsafeDocumentWrite !== void 0 ? { unsafeDocumentWrite: sb.unsafeDocumentWrite } : void 0;
			scf.renderHtml(liveContent.html, container, renderOpts).then((rendered) => {
				if (cancelled) {
					rendered.dispose();
					return;
				}
				frame = rendered;
				bridge = liveRef.current.createBridge({
					iframe: rendered.iframe,
					origin: rendered.origin,
					sendMessage: rendered.sendMessage
				}, { setHeight: (height) => {
					if (typeof height === "number" && Number.isFinite(height) && height > 0) setContentHeight(height);
				} });
				onMessage = (event) => {
					if (!isSandboxFrameMessage(event, rendered)) return;
					bridge?.onMessage(event);
				};
				window.addEventListener("message", onMessage);
				rendered.fullyLoadedPromiseWithTimeout(LOAD_TIMEOUT_MS).catch((err_0) => {
					if (cancelled) return;
					if (isShimLoadError(err_0) && err_0.code === "render-timeout") return;
					reportError(err_0);
				});
			}).catch((err_1) => {
				if (cancelled) return;
				frame?.dispose();
				frame = null;
				reportError(err_1);
			});
			return () => {
				cancelled = true;
				let cleanupFailed = false;
				let cleanupError;
				const runCleanup = (cleanup) => {
					try {
						cleanup();
					} catch (t6) {
						const error_0 = t6;
						if (cleanupFailed) console.error(error_0);
						else {
							cleanupFailed = true;
							cleanupError = error_0;
						}
					}
				};
				if (onMessage) {
					const listener = onMessage;
					onMessage = null;
					runCleanup(() => window.removeEventListener("message", listener));
				}
				const bridgeToDispose = bridge;
				bridge = null;
				if (bridgeToDispose) runCleanup(() => bridgeToDispose.dispose());
				const frameToDispose = frame;
				frame = null;
				if (frameToDispose) runCleanup(() => frameToDispose.dispose());
				runCleanup(() => setContentHeight(void 0));
				if (cleanupFailed) throw cleanupError;
			};
		};
		$[11] = t5;
	} else t5 = $[11];
	let t6;
	if ($[12] !== contentKey) {
		t6 = [contentKey];
		$[12] = contentKey;
		$[13] = t6;
	} else t6 = $[13];
	useEffect(t5, t6);
	const resolvedHeight = contentHeight != null ? Math.min(contentHeight, maxHeight) : void 0;
	let t7;
	if ($[14] !== resolvedHeight || $[15] !== sandbox?.style) {
		t7 = resolvedHeight != null ? {
			...sandbox?.style,
			height: resolvedHeight
		} : sandbox?.style;
		$[14] = resolvedHeight;
		$[15] = sandbox?.style;
		$[16] = t7;
	} else t7 = $[16];
	const mergedStyle = t7;
	const t8 = sandbox?.className;
	let t9;
	if ($[17] !== containerProps || $[18] !== mergedStyle || $[19] !== t8) {
		t9 = /* @__PURE__ */ jsx("div", {
			...containerProps,
			ref: containerRef,
			className: t8,
			style: mergedStyle
		});
		$[17] = containerProps;
		$[18] = mergedStyle;
		$[19] = t8;
		$[20] = t9;
	} else t9 = $[20];
	return t9;
}
//#endregion
export { SandboxHost, isSandboxFrameMessage };
