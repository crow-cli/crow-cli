"use client";
import { createMcpAppBridge } from "./bridge.js";
import { SandboxHost } from "../sandbox-host/SandboxHost.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useEffect, useLayoutEffect, useRef } from "@assistant-ui/tap/react-shim";
import { isRecord } from "@assistant-ui/core/internal";
import { jsx } from "react/jsx-runtime";
//#region src/mcp-apps/app-frame.tsx
const DEFAULT_PRODUCT = "assistant-ui-mcp-app";
const INIT_TIMEOUT_MS = 5e3;
const DEFAULT_MAX_HEIGHT = 800;
const isPlainObject = (value) => {
	if (!isRecord(value)) return false;
	const prototype = Object.getPrototypeOf(value);
	return prototype === null || prototype === Object.prototype;
};
const isSameHostContext = (a, b, depth = 0) => {
	if (Object.is(a, b)) return true;
	if (depth > 100) return false;
	if (Array.isArray(a) || Array.isArray(b)) {
		if (!Array.isArray(a) || !Array.isArray(b) || a.length !== b.length) return false;
		for (let i = 0; i < a.length; i++) if (!isSameHostContext(a[i], b[i], depth + 1)) return false;
		return true;
	}
	if (!isPlainObject(a) || !isPlainObject(b)) return false;
	const aKeys = Object.keys(a);
	return aKeys.length === Object.keys(b).length && aKeys.every((key) => Object.hasOwn(b, key) && isSameHostContext(a[key], b[key], depth + 1));
};
function useBridgeNotify(value, bridgeRef, widgetReadyRef, pendingRef, lastSentRef, notify, t0) {
	const $ = c(10);
	const isEqual = t0 === void 0 ? Object.is : t0;
	let t1;
	if ($[0] !== bridgeRef || $[1] !== isEqual || $[2] !== lastSentRef || $[3] !== notify || $[4] !== pendingRef || $[5] !== value || $[6] !== widgetReadyRef) {
		t1 = () => {
			if (!bridgeRef.current) return;
			if (value === void 0 || isEqual(lastSentRef.current, value)) {
				pendingRef.current = void 0;
				return;
			}
			if (!widgetReadyRef.current) {
				pendingRef.current = value;
				return;
			}
			notify(bridgeRef.current, value);
			lastSentRef.current = value;
		};
		$[0] = bridgeRef;
		$[1] = isEqual;
		$[2] = lastSentRef;
		$[3] = notify;
		$[4] = pendingRef;
		$[5] = value;
		$[6] = widgetReadyRef;
		$[7] = t1;
	} else t1 = $[7];
	let t2;
	if ($[8] !== value) {
		t2 = [value];
		$[8] = value;
		$[9] = t2;
	} else t2 = $[9];
	useEffect(t1, t2);
}
function buildLiveHandlers(initial, liveRef, lifecycle) {
	const live = () => liveRef.current.handlers;
	const has = (key) => initial?.[key] !== void 0;
	const out = {};
	Object.defineProperty(out, "allowedTools", {
		get: () => live()?.allowedTools,
		enumerable: true,
		configurable: true
	});
	const liveCall = (key) => ((p) => {
		const fn = live()?.[key];
		if (!fn) throw new Error(`${key} handler is no longer available`);
		return fn(p);
	});
	if (has("callTool")) out.callTool = liveCall("callTool");
	if (has("readResource")) out.readResource = liveCall("readResource");
	if (has("listResources")) out.listResources = liveCall("listResources");
	if (has("openLink")) out.openLink = liveCall("openLink");
	if (has("sendMessage")) out.sendMessage = liveCall("sendMessage");
	if (has("updateModelContext")) out.updateModelContext = liveCall("updateModelContext");
	if (has("requestDisplayMode")) out.requestDisplayMode = liveCall("requestDisplayMode");
	out.onSizeChange = (p) => {
		lifecycle.onSizeChange(p);
		live()?.onSizeChange?.(p);
	};
	out.onInitialized = () => {
		lifecycle.onInitialized();
		live()?.onInitialized?.();
	};
	out.onRequestTeardown = (p) => live()?.onRequestTeardown?.(p);
	out.onLog = (p) => live()?.onLog?.(p);
	out.onError = (e) => live()?.onError?.(e);
	return out;
}
function McpAppFrame(t0) {
	const $ = c(29);
	const { app, resource, input, output, sandbox, handlers, hostInfo, hostContext, maxHeight: t1 } = t0;
	const maxHeight = t1 === void 0 ? DEFAULT_MAX_HEIGHT : t1;
	const bridgeRef = useRef(null);
	const lastSentInputRef = useRef(void 0);
	const lastSentOutputRef = useRef(void 0);
	const lastSentHostContextRef = useRef(void 0);
	const widgetReadyRef = useRef(false);
	const pendingInputRef = useRef(void 0);
	const pendingOutputRef = useRef(void 0);
	const pendingHostContextRef = useRef(void 0);
	let t2;
	if ($[0] !== handlers || $[1] !== hostContext || $[2] !== hostInfo || $[3] !== input || $[4] !== output) {
		t2 = {
			handlers,
			hostInfo,
			hostContext,
			input,
			output
		};
		$[0] = handlers;
		$[1] = hostContext;
		$[2] = hostInfo;
		$[3] = input;
		$[4] = output;
		$[5] = t2;
	} else t2 = $[5];
	const liveRef = useRef(t2);
	let t3;
	let t4;
	if ($[6] !== handlers || $[7] !== hostContext || $[8] !== hostInfo || $[9] !== input || $[10] !== output) {
		t3 = () => {
			liveRef.current = {
				handlers,
				hostInfo,
				hostContext,
				input,
				output
			};
		};
		t4 = [
			handlers,
			hostInfo,
			hostContext,
			input,
			output
		];
		$[6] = handlers;
		$[7] = hostContext;
		$[8] = hostInfo;
		$[9] = input;
		$[10] = output;
		$[11] = t3;
		$[12] = t4;
	} else {
		t3 = $[11];
		t4 = $[12];
	}
	useLayoutEffect(t3, t4);
	let t5;
	if ($[13] === Symbol.for("react.memo_cache_sentinel")) {
		t5 = (frame, host) => {
			const current = liveRef.current;
			let initTimeoutId = null;
			const flushPending = () => {
				if (widgetReadyRef.current) return;
				widgetReadyRef.current = true;
				const b = bridgeRef.current;
				if (!b) return;
				if (pendingInputRef.current !== void 0) {
					b.notifyToolInput(pendingInputRef.current);
					lastSentInputRef.current = pendingInputRef.current;
					pendingInputRef.current = void 0;
				}
				if (pendingOutputRef.current !== void 0) {
					b.notifyToolResult(pendingOutputRef.current);
					lastSentOutputRef.current = pendingOutputRef.current;
					pendingOutputRef.current = void 0;
				}
				if (pendingHostContextRef.current !== void 0) {
					b.notifyHostContextChanged(pendingHostContextRef.current);
					lastSentHostContextRef.current = pendingHostContextRef.current;
					pendingHostContextRef.current = void 0;
				}
			};
			const wrappedHandlers = buildLiveHandlers(current.handlers, liveRef, {
				onInitialized: () => {
					if (initTimeoutId !== null) {
						clearTimeout(initTimeoutId);
						initTimeoutId = null;
					}
					flushPending();
				},
				onSizeChange: (p) => {
					if (p.height != null) host.setHeight(p.height);
				}
			});
			initTimeoutId = setTimeout(() => {
				initTimeoutId = null;
				flushPending();
			}, INIT_TIMEOUT_MS);
			const bridge = createMcpAppBridge({
				frame,
				handlers: wrappedHandlers,
				hostInfo: current.hostInfo,
				hostContext: current.hostContext
			});
			bridgeRef.current = bridge;
			if (current.input !== void 0) pendingInputRef.current = current.input;
			if (current.output !== void 0) pendingOutputRef.current = current.output;
			lastSentHostContextRef.current = current.hostContext ?? {};
			return {
				onMessage: bridge.onMessage,
				dispose: () => {
					if (initTimeoutId !== null) {
						clearTimeout(initTimeoutId);
						initTimeoutId = null;
					}
					bridge.dispose();
					bridgeRef.current = null;
					lastSentInputRef.current = void 0;
					lastSentOutputRef.current = void 0;
					lastSentHostContextRef.current = void 0;
					widgetReadyRef.current = false;
					pendingInputRef.current = void 0;
					pendingOutputRef.current = void 0;
					pendingHostContextRef.current = void 0;
				}
			};
		};
		$[13] = t5;
	} else t5 = $[13];
	const createBridge = t5;
	useBridgeNotify(input, bridgeRef, widgetReadyRef, pendingInputRef, lastSentInputRef, _temp);
	useBridgeNotify(output, bridgeRef, widgetReadyRef, pendingOutputRef, lastSentOutputRef, _temp2);
	useBridgeNotify(hostContext, bridgeRef, widgetReadyRef, pendingHostContextRef, lastSentHostContextRef, _temp3, isSameHostContext);
	let t6;
	if ($[14] !== resource.html) {
		t6 = { html: resource.html };
		$[14] = resource.html;
		$[15] = t6;
	} else t6 = $[15];
	const t7 = app.serverId ? `${app.serverId} ${resource.uri}` : resource.uri;
	const t8 = sandbox?.product ?? DEFAULT_PRODUCT;
	let t9;
	if ($[16] !== sandbox || $[17] !== t8) {
		t9 = {
			...sandbox,
			product: t8
		};
		$[16] = sandbox;
		$[17] = t8;
		$[18] = t9;
	} else t9 = $[18];
	let t10;
	if ($[19] === Symbol.for("react.memo_cache_sentinel")) {
		t10 = (err) => liveRef.current.handlers?.onError?.(err);
		$[19] = t10;
	} else t10 = $[19];
	const t11 = resource.meta?.prefersBorder ? "" : void 0;
	let t12;
	if ($[20] !== app.resourceUri || $[21] !== t11) {
		t12 = {
			"data-mcp-app-resource": app.resourceUri,
			"data-mcp-app-prefers-border": t11
		};
		$[20] = app.resourceUri;
		$[21] = t11;
		$[22] = t12;
	} else t12 = $[22];
	let t13;
	if ($[23] !== maxHeight || $[24] !== t12 || $[25] !== t6 || $[26] !== t7 || $[27] !== t9) {
		t13 = /* @__PURE__ */ jsx(SandboxHost, {
			content: t6,
			contentKey: t7,
			sandbox: t9,
			maxHeight,
			createBridge,
			onError: t10,
			containerProps: t12
		});
		$[23] = maxHeight;
		$[24] = t12;
		$[25] = t6;
		$[26] = t7;
		$[27] = t9;
		$[28] = t13;
	} else t13 = $[28];
	return t13;
}
function _temp3(b_2, v_1) {
	return b_2.notifyHostContextChanged(v_1);
}
function _temp2(b_1, v_0) {
	return b_1.notifyToolResult(v_0);
}
function _temp(b_0, v) {
	return b_0.notifyToolInput(v);
}
//#endregion
export { McpAppFrame };
