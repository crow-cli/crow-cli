import { nullProtoRecord } from "../../utils/record.js";
import { runCleanups } from "../../subscribable/subscribable.js";
import { ModelContext } from "../../store/clients/model-context-client.js";
import { isStandaloneToolDisplay, makeToolCallTextComponent } from "../model-context/toolbox.js";
import { attachTransformScopes, useAssistantClientRef, useAssistantScopeEffect } from "@assistant-ui/store/client";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useEffect, useState } from "@assistant-ui/tap/react-shim";
import { resource, useResources, withKey } from "@assistant-ui/tap";
//#region src/react/client/Tools.ts
/**
* Registers tools with model context and installs tool-call renderers.
*
* Mount this resource near an assistant subtree when you want to expose a
* group of tools declaratively. Tool definitions are registered with model
* context, while each tool renderer is registered with the tools scope for
* message rendering.
*/
const useTools = (t0) => {
	const $ = c(16);
	const { toolkit, mcpApp } = t0;
	let t1;
	if ($[0] !== mcpApp) {
		t1 = mcpApp ? [withKey("mcpApp", mcpApp)] : [];
		$[0] = mcpApp;
		$[1] = t1;
	} else t1 = $[1];
	const mcpAppOutput = useResources(t1)[0];
	const [toolUIs, setToolUIs] = useState(_temp);
	let t2;
	if ($[2] !== mcpAppOutput || $[3] !== toolUIs) {
		t2 = {
			toolUIs,
			mcpApp: mcpAppOutput
		};
		$[2] = mcpAppOutput;
		$[3] = toolUIs;
		$[4] = t2;
	} else t2 = $[4];
	const state = t2;
	const clientRef = useAssistantClientRef();
	let t3;
	if ($[5] === Symbol.for("react.memo_cache_sentinel")) {
		t3 = (toolName, render, options) => {
			const registration = {
				render,
				renderText: options?.renderText,
				standalone: options?.standalone ?? false
			};
			setToolUIs((prev) => {
				const next = nullProtoRecord(prev);
				next[toolName] = [...next[toolName] ?? [], registration];
				return next;
			});
			return () => {
				setToolUIs((prev_0) => {
					const registrations = prev_0[toolName]?.filter((r) => r !== registration) ?? [];
					const next_0 = nullProtoRecord(prev_0);
					if (registrations.length > 0) {
						next_0[toolName] = registrations;
						return next_0;
					}
					delete next_0[toolName];
					return next_0;
				});
			};
		};
		$[5] = t3;
	} else t3 = $[5];
	const setToolUI = t3;
	let t4;
	let t5;
	if ($[6] !== toolkit) {
		t4 = () => {
			if (!toolkit) return;
			const unsubscribes = [];
			for (const [toolName_0, tool] of Object.entries(toolkit)) {
				const toolRender = "render" in tool ? tool.render : void 0;
				const toolRenderText = "renderText" in tool ? tool.renderText : void 0;
				const render_0 = toolRender ?? (toolRenderText ? makeToolCallTextComponent(toolRenderText) : void 0);
				if (render_0) unsubscribes.push(setToolUI(toolName_0, render_0, {
					standalone: isStandaloneToolDisplay(tool),
					renderText: toolRenderText
				}));
			}
			return () => runCleanups(unsubscribes);
		};
		t5 = [toolkit, setToolUI];
		$[6] = toolkit;
		$[7] = t4;
		$[8] = t5;
	} else {
		t4 = $[7];
		t5 = $[8];
	}
	useEffect(t4, t5);
	let t6;
	if ($[9] !== clientRef || $[10] !== toolkit) {
		t6 = () => {
			if (!toolkit) return;
			const toolsWithoutRender = Object.entries(toolkit).reduce(_temp2, nullProtoRecord());
			return clientRef.current.modelContext().register({ getModelContext: () => ({ tools: toolsWithoutRender }) });
		};
		$[9] = clientRef;
		$[10] = toolkit;
		$[11] = t6;
	} else t6 = $[11];
	let t7;
	if ($[12] !== toolkit) {
		t7 = [toolkit];
		$[12] = toolkit;
		$[13] = t7;
	} else t7 = $[13];
	useAssistantScopeEffect("modelContext", t6, t7);
	let t8;
	if ($[14] !== state) {
		t8 = {
			getState: () => state,
			setToolUI
		};
		$[14] = state;
		$[15] = t8;
	} else t8 = $[15];
	return t8;
};
const Tools = resource(useTools);
attachTransformScopes(useTools, (scopes, parent) => {
	if (!scopes.modelContext && parent.modelContext.source === null) scopes.modelContext = ModelContext();
});
function _temp() {
	return nullProtoRecord();
}
function _temp2(acc, t0) {
	const [name, tool_0] = t0;
	if (tool_0.type === "mcp") return acc;
	const { display: _display, render: _render, renderText: _renderText, ...rest } = tool_0;
	acc[name] = rest;
	return acc;
}
//#endregion
export { Tools };
