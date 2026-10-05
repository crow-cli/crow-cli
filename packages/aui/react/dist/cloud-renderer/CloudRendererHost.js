"use client";
import { AssistantRuntimeProvider } from "../legacy-runtime/AssistantRuntimeProvider.js";
import { useExternalStoreRuntime } from "../legacy-runtime/runtime-cores/external-store/useExternalStoreRuntime.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { ReadonlyThreadProvider } from "@assistant-ui/core/react";
import { Component, useEffect, useRef, useState, useSyncExternalStore } from "@assistant-ui/tap/react-shim";
import { AuiConfig, AuiProvider, useAui } from "@assistant-ui/store";
import { resource } from "@assistant-ui/tap";
import { jsx } from "react/jsx-runtime";
//#region src/cloud-renderer/CloudRendererHost.tsx
const CHANNEL = "assistant-ui/cloud-renderer";
const toOrigin = (value) => {
	try {
		const url = new URL(value);
		return url.protocol === "https:" || url.protocol === "http:" ? url.origin : void 0;
	} catch {
		return;
	}
};
const DEFAULT_ALLOWED_ORIGINS = ["https://cloud.assistant-ui.com"];
const INERT_STORE = {
	messages: [],
	isDisabled: true,
	onNew: async () => {}
};
var RenderBoundary = class extends Component {
	state = { failed: false };
	static getDerivedStateFromError() {
		return { failed: true };
	}
	componentDidCatch(error, _info) {
		this.props.onError(error);
	}
	render() {
		return this.state.failed ? null : this.props.children;
	}
};
const useReadonlyTools = (aui) => {
	const $ = c(7);
	const tools = useSyncExternalStore(aui.subscribe, aui.tools.getState);
	let t0;
	if ($[0] !== tools) {
		t0 = {
			...tools,
			mcpApp: void 0
		};
		$[0] = tools;
		$[1] = t0;
	} else t0 = $[1];
	const state = t0;
	let t1;
	if ($[2] !== state) {
		t1 = () => state;
		$[2] = state;
		$[3] = t1;
	} else t1 = $[3];
	let t2;
	if ($[4] !== aui.tools.setToolUI || $[5] !== t1) {
		t2 = {
			getState: t1,
			setToolUI: aui.tools.setToolUI
		};
		$[4] = aui.tools.setToolUI;
		$[5] = t1;
		$[6] = t2;
	} else t2 = $[6];
	return t2;
};
const ReadonlyTools = resource(useReadonlyTools);
const SuppressMcpApps = (t0) => {
	const $ = c(6);
	const { children } = t0;
	const aui = useAui();
	let t1;
	if ($[0] !== aui) {
		t1 = AuiConfig({ tools: ReadonlyTools(aui) });
		$[0] = aui;
		$[1] = t1;
	} else t1 = $[1];
	let t2;
	if ($[2] !== aui || $[3] !== children || $[4] !== t1) {
		t2 = /* @__PURE__ */ jsx(AuiProvider, {
			extends: aui,
			config: t1,
			children
		});
		$[2] = aui;
		$[3] = children;
		$[4] = t1;
		$[5] = t2;
	} else t2 = $[5];
	return t2;
};
const ReadonlyConversation = (t0) => {
	const $ = c(12);
	const { messages, children, aui, config } = t0;
	const runtime = useExternalStoreRuntime(INERT_STORE);
	let t1;
	if ($[0] !== aui) {
		t1 = aui !== void 0 && { aui };
		$[0] = aui;
		$[1] = t1;
	} else t1 = $[1];
	let t2;
	if ($[2] !== config) {
		t2 = config !== void 0 && { config };
		$[2] = config;
		$[3] = t2;
	} else t2 = $[3];
	let t3;
	if ($[4] !== children || $[5] !== messages) {
		t3 = /* @__PURE__ */ jsx(SuppressMcpApps, { children: /* @__PURE__ */ jsx(ReadonlyThreadProvider, {
			messages,
			children
		}) });
		$[4] = children;
		$[5] = messages;
		$[6] = t3;
	} else t3 = $[6];
	let t4;
	if ($[7] !== runtime || $[8] !== t1 || $[9] !== t2 || $[10] !== t3) {
		t4 = /* @__PURE__ */ jsx(AssistantRuntimeProvider, {
			runtime,
			...t1,
			...t2,
			children: t3
		});
		$[7] = runtime;
		$[8] = t1;
		$[9] = t2;
		$[10] = t3;
		$[11] = t4;
	} else t4 = $[11];
	return t4;
};
function CloudRendererHost(t0) {
	const $ = c(18);
	const { children, allowedOrigins: t1, aui, config } = t0;
	const allowedOrigins = t1 === void 0 ? DEFAULT_ALLOWED_ORIGINS : t1;
	const rootRef = useRef(null);
	const connectedOrigin = useRef(null);
	const [render, setRender] = useState(null);
	let t2;
	if ($[0] !== allowedOrigins) {
		t2 = allowedOrigins.flatMap(_temp).join(" ");
		$[0] = allowedOrigins;
		$[1] = t2;
	} else t2 = $[1];
	const originsKey = t2;
	let t3;
	let t4;
	if ($[2] !== originsKey) {
		t3 = () => {
			const origins = originsKey ? originsKey.split(" ") : [];
			if (connectedOrigin.current !== null && !origins.includes(connectedOrigin.current)) connectedOrigin.current = null;
			const post = _temp2;
			for (const origin_0 of origins) post(origin_0, {
				channel: CHANNEL,
				version: 1,
				type: "ready"
			});
			const onMessage = (event) => {
				if (event.source !== window.parent || !origins.includes(event.origin)) return;
				const data = event.data;
				if (typeof data !== "object" || data === null) return;
				const message_0 = data;
				if (message_0.channel !== CHANNEL || message_0.version !== 1 || message_0.type !== "render" || !Array.isArray(message_0.messages)) return;
				if (connectedOrigin.current !== null && connectedOrigin.current !== event.origin) return;
				connectedOrigin.current = event.origin;
				setRender((previous) => ({
					messages: message_0.messages,
					revision: (previous?.revision ?? 0) + 1
				}));
			};
			window.addEventListener("message", onMessage);
			return () => window.removeEventListener("message", onMessage);
		};
		t4 = [originsKey];
		$[2] = originsKey;
		$[3] = t3;
		$[4] = t4;
	} else {
		t3 = $[3];
		t4 = $[4];
	}
	useEffect(t3, t4);
	let t5;
	let t6;
	if ($[5] !== render) {
		t5 = () => {
			if (!render || !rootRef.current) return;
			const root = rootRef.current;
			let frame = 0;
			const report = () => {
				if (frame) return;
				frame = requestAnimationFrame(() => {
					frame = 0;
					const origin_1 = connectedOrigin.current;
					const height = root.getBoundingClientRect().height;
					if (origin_1 && Number.isFinite(height) && height >= 0) window.parent.postMessage({
						channel: CHANNEL,
						version: 1,
						type: "size",
						height
					}, origin_1);
				});
			};
			const observer = new ResizeObserver(report);
			observer.observe(root);
			report();
			return () => {
				observer.disconnect();
				cancelAnimationFrame(frame);
			};
		};
		t6 = [render];
		$[5] = render;
		$[6] = t5;
		$[7] = t6;
	} else {
		t5 = $[6];
		t6 = $[7];
	}
	useEffect(t5, t6);
	let t7;
	if ($[8] === Symbol.for("react.memo_cache_sentinel")) {
		t7 = (error) => {
			const origin_2 = connectedOrigin.current;
			if (origin_2) window.parent.postMessage({
				channel: CHANNEL,
				version: 1,
				type: "error",
				message: error.message
			}, origin_2);
		};
		$[8] = t7;
	} else t7 = $[8];
	const reportError = t7;
	let t8;
	let t9;
	if ($[9] === Symbol.for("react.memo_cache_sentinel")) {
		t8 = (node) => {
			rootRef.current = node;
			if (node) node.inert = true;
		};
		t9 = { width: "100%" };
		$[9] = t8;
		$[10] = t9;
	} else {
		t8 = $[9];
		t9 = $[10];
	}
	let t10;
	if ($[11] !== aui || $[12] !== children || $[13] !== config || $[14] !== render) {
		t10 = render && /* @__PURE__ */ jsx(RenderBoundary, {
			onError: reportError,
			children: /* @__PURE__ */ jsx(ReadonlyConversation, {
				messages: render.messages,
				aui,
				config,
				children
			})
		}, render.revision);
		$[11] = aui;
		$[12] = children;
		$[13] = config;
		$[14] = render;
		$[15] = t10;
	} else t10 = $[15];
	let t11;
	if ($[16] !== t10) {
		t11 = /* @__PURE__ */ jsx("div", {
			ref: t8,
			style: t9,
			children: t10
		});
		$[16] = t10;
		$[17] = t11;
	} else t11 = $[17];
	return t11;
}
function _temp2(origin, message) {
	return window.parent.postMessage(message, origin);
}
function _temp(value) {
	return toOrigin(value) ?? [];
}
//#endregion
export { CloudRendererHost };
