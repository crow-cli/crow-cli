import { toWebMcpTool } from "./convertTools.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useEffect, useRef, useState } from "@assistant-ui/tap/react-shim";
import { resource } from "@assistant-ui/tap";
//#region src/unstable/webmcp/WebMcpRegistrationResource.ts
const notPermitted = (error) => error?.name === "NotAllowedError";
const notPermittedMessage = (name) => `[assistant-ui] WebMCP registration for tool "${name}" was not permitted; the page's tools permission is disabled.`;
const useWebMcpRegistration = (t0) => {
	const $ = c(11);
	const { host, name, signature, tool, getCurrentTool } = t0;
	const [refused, setRefused] = useState(false);
	const fallbackToolRef = useRef(tool);
	let t1;
	if ($[0] !== getCurrentTool || $[1] !== host || $[2] !== name || $[3] !== refused) {
		t1 = () => {
			if (refused) return;
			const lifecycle = new AbortController();
			let live = true;
			let dispose;
			const refuse = (message, error) => {
				if (!live) return;
				live = false;
				setRefused(true);
				console.warn(message, error);
			};
			try {
				dispose = host.registerTool(toWebMcpTool(name, () => getCurrentTool(name) ?? fallbackToolRef.current, lifecycle.signal), (error_1) => refuse(notPermitted(error_1) ? notPermittedMessage(name) : `[assistant-ui] WebMCP registration for tool "${name}" failed (name may already be registered).`, error_1));
			} catch (t2) {
				const error_0 = t2;
				refuse(notPermitted(error_0) ? notPermittedMessage(name) : `[assistant-ui] Skipping WebMCP registration for tool "${name}": registerTool failed (name may already be registered).`, error_0);
				return;
			}
			return () => {
				live = false;
				lifecycle.abort();
				try {
					dispose();
				} catch (t3) {
					const error_2 = t3;
					console.warn(`[assistant-ui] Unregistering WebMCP tool "${name}" failed.`, error_2);
				}
			};
		};
		$[0] = getCurrentTool;
		$[1] = host;
		$[2] = name;
		$[3] = refused;
		$[4] = t1;
	} else t1 = $[4];
	let t2;
	if ($[5] !== getCurrentTool || $[6] !== host || $[7] !== name || $[8] !== refused || $[9] !== signature) {
		t2 = [
			getCurrentTool,
			host,
			name,
			signature,
			refused
		];
		$[5] = getCurrentTool;
		$[6] = host;
		$[7] = name;
		$[8] = refused;
		$[9] = signature;
		$[10] = t2;
	} else t2 = $[10];
	useEffect(t1, t2);
	return refused ? null : name;
};
const WebMcpRegistrationResource = resource(useWebMcpRegistration);
//#endregion
export { WebMcpRegistrationResource };
