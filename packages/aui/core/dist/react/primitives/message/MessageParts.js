import { isMcpAppUri } from "../../../types/message.js";
import { getMessagePartKeys } from "../../../utils/getMessagePartKeys.js";
import { PartByIndexProvider } from "../../providers/PartByIndexProvider.js";
import { TextMessagePartProvider } from "../../providers/TextMessagePartProvider.js";
import { ChainOfThoughtByIndicesProvider } from "../../providers/ChainOfThoughtByIndicesProvider.js";
import { getMessageQuote } from "../../utils/getMessageQuote.js";
import { GenerativeUIRender } from "../generativeUI/GenerativeUI.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { memo } from "@assistant-ui/tap/react-shim";
import { RenderChildrenWithAccessor, useAui, useAuiState } from "@assistant-ui/store";
import { useShallowSelector } from "@assistant-ui/store/internal";
import { Fragment as Fragment$1, jsx, jsxs } from "react/jsx-runtime";
//#region src/react/primitives/message/MessageParts.tsx
/**
* Creates a group state manager for a specific part type.
* Returns functions to start, end, and finalize groups.
*/
const createGroupState = (groupType) => {
	let start = -1;
	return {
		startGroup: (index) => {
			if (start === -1) start = index;
		},
		endGroup: (endIndex, ranges) => {
			if (start !== -1) {
				ranges.push({
					type: groupType,
					startIndex: start,
					endIndex
				});
				start = -1;
			}
		},
		finalize: (endIndex, ranges) => {
			if (start !== -1) ranges.push({
				type: groupType,
				startIndex: start,
				endIndex
			});
		}
	};
};
/**
* Groups consecutive tool-call and reasoning message parts into ranges.
* Always groups tool calls and reasoning parts, even if there's only one.
* When useChainOfThought is true, groups tool-call and reasoning parts together.
*/
const groupMessageParts = (messageTypes, useChainOfThought, partIds) => {
	const ranges = [];
	if (useChainOfThought) {
		const chainOfThoughtGroup = createGroupState("chainOfThoughtGroup");
		for (let i = 0; i < messageTypes.length; i++) {
			const type = messageTypes[i];
			if (type === "tool-call" || type === "reasoning") chainOfThoughtGroup.startGroup(i);
			else {
				chainOfThoughtGroup.endGroup(i - 1, ranges);
				ranges.push({
					type: "single",
					index: i
				});
			}
		}
		chainOfThoughtGroup.finalize(messageTypes.length - 1, ranges);
	} else {
		const toolGroup = createGroupState("toolGroup");
		const reasoningGroup = createGroupState("reasoningGroup");
		for (let i = 0; i < messageTypes.length; i++) {
			const type = messageTypes[i];
			if (type === "tool-call") {
				reasoningGroup.endGroup(i - 1, ranges);
				toolGroup.startGroup(i);
			} else if (type === "reasoning") {
				toolGroup.endGroup(i - 1, ranges);
				reasoningGroup.startGroup(i);
			} else {
				toolGroup.endGroup(i - 1, ranges);
				reasoningGroup.endGroup(i - 1, ranges);
				ranges.push({
					type: "single",
					index: i
				});
			}
		}
		toolGroup.finalize(messageTypes.length - 1, ranges);
		reasoningGroup.finalize(messageTypes.length - 1, ranges);
	}
	if (partIds) {
		const claimed = /* @__PURE__ */ new Set();
		for (const range of ranges) {
			if (range.type === "single") continue;
			const id = partIds[range.startIndex];
			if (id?.includes(":") && !claimed.has(id)) {
				claimed.add(id);
				range.idKey = `id:${id}`;
			}
		}
	}
	return ranges;
};
const useMessagePartsGroups = (useChainOfThought) => {
	const $ = c(10);
	const messageTypes = useAuiState(useShallowSelector(_temp2));
	const partIds = useAuiState(useShallowSelector(_temp3));
	let t0;
	bb0: {
		if (messageTypes.length === 0) {
			let t1;
			if ($[0] === Symbol.for("react.memo_cache_sentinel")) {
				t1 = [];
				$[0] = t1;
			} else t1 = $[0];
			let t2;
			if ($[1] !== partIds) {
				t2 = {
					ranges: t1,
					partIds
				};
				$[1] = partIds;
				$[2] = t2;
			} else t2 = $[2];
			t0 = t2;
			break bb0;
		}
		let t1;
		if ($[3] !== messageTypes || $[4] !== partIds || $[5] !== useChainOfThought) {
			t1 = groupMessageParts(messageTypes, useChainOfThought, partIds);
			$[3] = messageTypes;
			$[4] = partIds;
			$[5] = useChainOfThought;
			$[6] = t1;
		} else t1 = $[6];
		let t2;
		if ($[7] !== partIds || $[8] !== t1) {
			t2 = {
				ranges: t1,
				partIds
			};
			$[7] = partIds;
			$[8] = t1;
			$[9] = t2;
		} else t2 = $[9];
		t0 = t2;
	}
	return t0;
};
const ToolUIDisplay = (t0) => {
	const $ = c(9);
	let Fallback;
	let props;
	if ($[0] !== t0) {
		({Fallback, ...props} = t0);
		$[0] = t0;
		$[1] = Fallback;
		$[2] = props;
	} else {
		Fallback = $[1];
		props = $[2];
	}
	let t1;
	if ($[3] !== Fallback || $[4] !== props.toolName) {
		t1 = (s) => s.tools.toolUIs[props.toolName]?.[0]?.render ?? Fallback;
		$[3] = Fallback;
		$[4] = props.toolName;
		$[5] = t1;
	} else t1 = $[5];
	const Render = useAuiState(t1);
	if (!Render) return null;
	let t2;
	if ($[6] !== Render || $[7] !== props) {
		t2 = /* @__PURE__ */ jsx(Render, { ...props });
		$[6] = Render;
		$[7] = props;
		$[8] = t2;
	} else t2 = $[8];
	return t2;
};
const getDataRenderer = (dataRenderers, name, inlineFallback) => {
	const named = dataRenderers.renderers[name]?.[0];
	if (named) return named;
	return dataRenderers.fallbacks[0] ?? inlineFallback;
};
const DataUIDisplay = (t0) => {
	const $ = c(9);
	let Fallback;
	let props;
	if ($[0] !== t0) {
		({Fallback, ...props} = t0);
		$[0] = t0;
		$[1] = Fallback;
		$[2] = props;
	} else {
		Fallback = $[1];
		props = $[2];
	}
	let t1;
	if ($[3] !== Fallback || $[4] !== props.name) {
		t1 = (s) => getDataRenderer(s.dataRenderers, props.name, Fallback);
		$[3] = Fallback;
		$[4] = props.name;
		$[5] = t1;
	} else t1 = $[5];
	const Render = useAuiState(t1);
	if (!Render) return null;
	let t2;
	if ($[6] !== Render || $[7] !== props) {
		t2 = /* @__PURE__ */ jsx(Render, { ...props });
		$[6] = Render;
		$[7] = props;
		$[8] = t2;
	} else t2 = $[8];
	return t2;
};
/**
* Platform-agnostic no-op default components.
* Each platform (web, RN) wraps MessagePrimitiveParts with its own defaults.
*/
const defaultComponents = {
	Text: () => null,
	Reasoning: () => null,
	Source: () => null,
	Image: () => null,
	File: () => null,
	Unstable_Audio: () => null,
	ToolGroup: ({ children }) => children,
	ReasoningGroup: ({ children }) => children
};
const MessagePartComponent = (t0) => {
	const $ = c(54);
	const { components: t1 } = t0;
	let t2;
	if ($[0] !== t1) {
		t2 = t1 === void 0 ? {} : t1;
		$[0] = t1;
		$[1] = t2;
	} else t2 = $[1];
	const { Text: t3, Reasoning: t4, Image: t5, Source: t6, File: t7, Unstable_Audio: t8, tools: t9, data, generativeUI } = t2;
	const Text = t3 === void 0 ? defaultComponents.Text : t3;
	const Reasoning = t4 === void 0 ? defaultComponents.Reasoning : t4;
	const Image = t5 === void 0 ? defaultComponents.Image : t5;
	const Source = t6 === void 0 ? defaultComponents.Source : t6;
	const File = t7 === void 0 ? defaultComponents.File : t7;
	const Audio = t8 === void 0 ? defaultComponents.Unstable_Audio : t8;
	let t10;
	if ($[2] !== t9) {
		t10 = t9 === void 0 ? {} : t9;
		$[2] = t9;
		$[3] = t10;
	} else t10 = $[3];
	const tools = t10;
	const aui = useAui();
	const part = useAuiState(_temp4);
	const type = part.type;
	if (type === "tool-call") {
		const addResult = aui.part.addToolResult;
		const resume = aui.part.resumeToolCall;
		const respondToApproval = aui.part.respondToToolApproval;
		const unstable_recordInteraction = aui.part.unstable_recordInteraction;
		if ("Override" in tools) {
			let t11;
			if ($[4] !== unstable_recordInteraction) {
				t11 = unstable_recordInteraction && { unstable_recordInteraction };
				$[4] = unstable_recordInteraction;
				$[5] = t11;
			} else t11 = $[5];
			let t12;
			if ($[6] !== addResult || $[7] !== part || $[8] !== respondToApproval || $[9] !== resume || $[10] !== t11 || $[11] !== tools.Override) {
				t12 = /* @__PURE__ */ jsx(tools.Override, {
					...part,
					addResult,
					resume,
					respondToApproval,
					...t11
				});
				$[6] = addResult;
				$[7] = part;
				$[8] = respondToApproval;
				$[9] = resume;
				$[10] = t11;
				$[11] = tools.Override;
				$[12] = t12;
			} else t12 = $[12];
			return t12;
		}
		let t11;
		if ($[13] !== part.toolName || $[14] !== tools.Fallback || $[15] !== tools.by_name) {
			t11 = (tools.by_name && Object.hasOwn(tools.by_name, part.toolName) ? tools.by_name[part.toolName] : void 0) ?? tools.Fallback;
			$[13] = part.toolName;
			$[14] = tools.Fallback;
			$[15] = tools.by_name;
			$[16] = t11;
		} else t11 = $[16];
		const Tool = t11;
		let t12;
		if ($[17] !== unstable_recordInteraction) {
			t12 = unstable_recordInteraction && { unstable_recordInteraction };
			$[17] = unstable_recordInteraction;
			$[18] = t12;
		} else t12 = $[18];
		let t13;
		if ($[19] !== Tool || $[20] !== addResult || $[21] !== part || $[22] !== respondToApproval || $[23] !== resume || $[24] !== t12) {
			t13 = /* @__PURE__ */ jsx(ToolUIDisplay, {
				...part,
				Fallback: Tool,
				addResult,
				resume,
				respondToApproval,
				...t12
			});
			$[19] = Tool;
			$[20] = addResult;
			$[21] = part;
			$[22] = respondToApproval;
			$[23] = resume;
			$[24] = t12;
			$[25] = t13;
		} else t13 = $[25];
		return t13;
	}
	if (part.status?.type === "requires-action") throw new Error("Encountered unexpected requires-action status");
	switch (type) {
		case "text": {
			let t11;
			if ($[26] !== Text || $[27] !== part) {
				t11 = /* @__PURE__ */ jsx(Text, { ...part });
				$[26] = Text;
				$[27] = part;
				$[28] = t11;
			} else t11 = $[28];
			return t11;
		}
		case "reasoning": {
			let t11;
			if ($[29] !== Reasoning || $[30] !== part) {
				t11 = /* @__PURE__ */ jsx(Reasoning, { ...part });
				$[29] = Reasoning;
				$[30] = part;
				$[31] = t11;
			} else t11 = $[31];
			return t11;
		}
		case "source": {
			let t11;
			if ($[32] !== Source || $[33] !== part) {
				t11 = /* @__PURE__ */ jsx(Source, { ...part });
				$[32] = Source;
				$[33] = part;
				$[34] = t11;
			} else t11 = $[34];
			return t11;
		}
		case "image": {
			let t11;
			if ($[35] !== Image || $[36] !== part) {
				t11 = /* @__PURE__ */ jsx(Image, { ...part });
				$[35] = Image;
				$[36] = part;
				$[37] = t11;
			} else t11 = $[37];
			return t11;
		}
		case "file": {
			let t11;
			if ($[38] !== File || $[39] !== part) {
				t11 = /* @__PURE__ */ jsx(File, { ...part });
				$[38] = File;
				$[39] = part;
				$[40] = t11;
			} else t11 = $[40];
			return t11;
		}
		case "audio": {
			let t11;
			if ($[41] !== Audio || $[42] !== part) {
				t11 = /* @__PURE__ */ jsx(Audio, { ...part });
				$[41] = Audio;
				$[42] = part;
				$[43] = t11;
			} else t11 = $[43];
			return t11;
		}
		case "data": {
			let t11;
			if ($[44] !== data || $[45] !== part.name) {
				t11 = (data?.by_name && Object.hasOwn(data.by_name, part.name) ? data.by_name[part.name] : void 0) ?? data?.Fallback;
				$[44] = data;
				$[45] = part.name;
				$[46] = t11;
			} else t11 = $[46];
			const Data = t11;
			let t12;
			if ($[47] !== Data || $[48] !== part) {
				t12 = /* @__PURE__ */ jsx(DataUIDisplay, {
					...part,
					Fallback: Data
				});
				$[47] = Data;
				$[48] = part;
				$[49] = t12;
			} else t12 = $[49];
			return t12;
		}
		case "generative-ui": {
			if (!generativeUI?.components) {
				if (typeof process !== "undefined" && process.env?.NODE_ENV !== "production") console.warn("MessagePrimitive.Parts received a generative-ui part but no `components.generativeUI.components` allowlist was provided. Pass an allowlist or render with <MessagePrimitive.GenerativeUI />.");
				return null;
			}
			const t11 = part;
			let t12;
			if ($[50] !== generativeUI.Fallback || $[51] !== generativeUI.components || $[52] !== t11.spec) {
				t12 = /* @__PURE__ */ jsx(GenerativeUIRender, {
					spec: t11.spec,
					components: generativeUI.components,
					Fallback: generativeUI.Fallback
				});
				$[50] = generativeUI.Fallback;
				$[51] = generativeUI.components;
				$[52] = t11.spec;
				$[53] = t12;
			} else t12 = $[53];
			return t12;
		}
		default:
			console.warn(`Unknown message part type: ${type}`);
			return null;
	}
};
/**
* Renders a single message part at the specified index.
*/
const MessagePrimitivePartByIndex = memo((t0) => {
	const $ = c(5);
	const { index, components } = t0;
	let t1;
	if ($[0] !== components) {
		t1 = /* @__PURE__ */ jsx(MessagePartComponent, { components });
		$[0] = components;
		$[1] = t1;
	} else t1 = $[1];
	let t2;
	if ($[2] !== index || $[3] !== t1) {
		t2 = /* @__PURE__ */ jsx(PartByIndexProvider, {
			index,
			children: t1
		});
		$[2] = index;
		$[3] = t1;
		$[4] = t2;
	} else t2 = $[4];
	return t2;
}, (prev, next) => prev.index === next.index && prev.components?.Text === next.components?.Text && prev.components?.Reasoning === next.components?.Reasoning && prev.components?.Source === next.components?.Source && prev.components?.Image === next.components?.Image && prev.components?.File === next.components?.File && prev.components?.Unstable_Audio === next.components?.Unstable_Audio && prev.components?.tools === next.components?.tools && prev.components?.data === next.components?.data && prev.components?.generativeUI === next.components?.generativeUI && prev.components?.ToolGroup === next.components?.ToolGroup && prev.components?.ReasoningGroup === next.components?.ReasoningGroup);
MessagePrimitivePartByIndex.displayName = "MessagePrimitive.PartByIndex";
const EmptyPartFallback = (t0) => {
	const $ = c(6);
	const { status, component: Component } = t0;
	const t1 = status.type === "running";
	let t2;
	if ($[0] !== Component || $[1] !== status) {
		t2 = /* @__PURE__ */ jsx(Component, {
			type: "text",
			text: "",
			status
		});
		$[0] = Component;
		$[1] = status;
		$[2] = t2;
	} else t2 = $[2];
	let t3;
	if ($[3] !== t1 || $[4] !== t2) {
		t3 = /* @__PURE__ */ jsx(TextMessagePartProvider, {
			text: "",
			isRunning: t1,
			children: t2
		});
		$[3] = t1;
		$[4] = t2;
		$[5] = t3;
	} else t3 = $[5];
	return t3;
};
const COMPLETE_STATUS = Object.freeze({ type: "complete" });
const RUNNING_STATUS = Object.freeze({ type: "running" });
const EmptyPartsImpl = (t0) => {
	const $ = c(6);
	const { components } = t0;
	const status = useAuiState(_temp5);
	if (components?.Empty) {
		let t1;
		if ($[0] !== components.Empty || $[1] !== status) {
			t1 = /* @__PURE__ */ jsx(components.Empty, { status });
			$[0] = components.Empty;
			$[1] = status;
			$[2] = t1;
		} else t1 = $[2];
		return t1;
	}
	if (status.type !== "running") return null;
	const t1 = components?.Text ?? defaultComponents.Text;
	let t2;
	if ($[3] !== status || $[4] !== t1) {
		t2 = /* @__PURE__ */ jsx(EmptyPartFallback, {
			status,
			component: t1
		});
		$[3] = status;
		$[4] = t1;
		$[5] = t2;
	} else t2 = $[5];
	return t2;
};
const EmptyParts = memo(EmptyPartsImpl, (prev, next) => prev.components?.Empty === next.components?.Empty && prev.components?.Text === next.components?.Text);
const ConditionalEmptyImpl = (t0) => {
	const $ = c(4);
	const { components, enabled } = t0;
	let t1;
	if ($[0] !== enabled) {
		t1 = (s) => {
			if (!enabled) return false;
			if (s.message.parts.length === 0) return false;
			const lastPart = s.message.parts[s.message.parts.length - 1];
			return lastPart?.type !== "text" && lastPart?.type !== "reasoning";
		};
		$[0] = enabled;
		$[1] = t1;
	} else t1 = $[1];
	if (!useAuiState(t1)) return null;
	let t2;
	if ($[2] !== components) {
		t2 = /* @__PURE__ */ jsx(EmptyParts, { components });
		$[2] = components;
		$[3] = t2;
	} else t2 = $[3];
	return t2;
};
const ConditionalEmpty = memo(ConditionalEmptyImpl, (prev, next) => prev.enabled === next.enabled && prev.components?.Empty === next.components?.Empty && prev.components?.Text === next.components?.Text);
const QuoteRendererImpl = (t0) => {
	const $ = c(4);
	const { Quote } = t0;
	const quoteInfo = useAuiState(getMessageQuote);
	if (!quoteInfo) return null;
	let t1;
	if ($[0] !== Quote || $[1] !== quoteInfo.messageId || $[2] !== quoteInfo.text) {
		t1 = /* @__PURE__ */ jsx(Quote, {
			text: quoteInfo.text,
			messageId: quoteInfo.messageId
		});
		$[0] = Quote;
		$[1] = quoteInfo.messageId;
		$[2] = quoteInfo.text;
		$[3] = t1;
	} else t1 = $[3];
	return t1;
};
const QuoteRenderer = memo(QuoteRendererImpl);
function resolveToolRender(toolsState, part) {
	const named = toolsState.toolUIs[part.toolName]?.[0]?.render ?? null;
	if (named) return named;
	if (isMcpAppUri(part.mcp?.app?.resourceUri) && toolsState.mcpApp) return toolsState.mcpApp.render;
	return null;
}
/**
* Stable propless component that renders the registered tool UI for the
* current part context. Reads tool registry and part state from context.
*/
const RegisteredToolUI = () => {
	const $ = c(9);
	const aui = useAui();
	const part = useAuiState(_temp6);
	const Render = useAuiState(_temp7);
	const unstable_recordInteraction = aui.part.unstable_recordInteraction;
	if (!Render || part.type !== "tool-call") return null;
	let t0;
	if ($[0] !== unstable_recordInteraction) {
		t0 = unstable_recordInteraction && { unstable_recordInteraction };
		$[0] = unstable_recordInteraction;
		$[1] = t0;
	} else t0 = $[1];
	let t1;
	if ($[2] !== Render || $[3] !== aui.part.addToolResult || $[4] !== aui.part.respondToToolApproval || $[5] !== aui.part.resumeToolCall || $[6] !== part || $[7] !== t0) {
		t1 = /* @__PURE__ */ jsx(Render, {
			...part,
			addResult: aui.part.addToolResult,
			resume: aui.part.resumeToolCall,
			respondToApproval: aui.part.respondToToolApproval,
			...t0
		});
		$[2] = Render;
		$[3] = aui.part.addToolResult;
		$[4] = aui.part.respondToToolApproval;
		$[5] = aui.part.resumeToolCall;
		$[6] = part;
		$[7] = t0;
		$[8] = t1;
	} else t1 = $[8];
	return t1;
};
/**
* Stable propless component that renders the registered data renderer UI
* for the current part context.
*/
const RegisteredDataRendererUI = () => {
	const $ = c(3);
	const part = useAuiState(_temp8);
	const Render = useAuiState(_temp9);
	if (!Render || part.type !== "data") return null;
	const t0 = part;
	let t1;
	if ($[0] !== Render || $[1] !== t0) {
		t1 = /* @__PURE__ */ jsx(Render, { ...t0 });
		$[0] = Render;
		$[1] = t0;
		$[2] = t1;
	} else t1 = $[2];
	return t1;
};
/**
* Fallback component rendered when the children render function returns null.
* Renders registered tool/data UIs via context.
* For all other part types, renders nothing.
*
* This allows users to write:
*   {({ part }) => {
*     if (part.type === "text") return <MyText />;
*     return null; // tool UIs and data UIs still render via registry
*   }}
*
* To explicitly render nothing (suppressing registered UIs), return <></>.
*/
const DefaultPartFallback = () => {
	const $ = c(2);
	const partType = useAuiState(_temp0);
	if (partType === "tool-call") {
		let t0;
		if ($[0] === Symbol.for("react.memo_cache_sentinel")) {
			t0 = /* @__PURE__ */ jsx(RegisteredToolUI, {});
			$[0] = t0;
		} else t0 = $[0];
		return t0;
	}
	if (partType === "data") {
		let t0;
		if ($[1] === Symbol.for("react.memo_cache_sentinel")) {
			t0 = /* @__PURE__ */ jsx(RegisteredDataRendererUI, {});
			$[1] = t0;
		} else t0 = $[1];
		return t0;
	}
	return null;
};
const EMPTY_RUNNING_TEXT_PART = Object.freeze({
	type: "text",
	text: "",
	status: RUNNING_STATUS
});
const MessagePartChildrenInner = ({ children }) => {
	const aui = useAui();
	const dataRenderers = useAuiState((s) => s.dataRenderers);
	return /* @__PURE__ */ jsx(RenderChildrenWithAccessor, {
		getItemState: (client) => client.part.getState(),
		children: (getItem) => children({ get part() {
			const state = getItem();
			if (state.type === "tool-call") {
				const hasUI = resolveToolRender(aui.tools.getState(), state) !== null;
				const partMethods = aui.part;
				return {
					...state,
					toolUI: hasUI ? /* @__PURE__ */ jsx(RegisteredToolUI, {}) : null,
					addResult: partMethods.addToolResult,
					resume: partMethods.resumeToolCall,
					respondToApproval: partMethods.respondToToolApproval,
					...partMethods.unstable_recordInteraction && { unstable_recordInteraction: partMethods.unstable_recordInteraction }
				};
			}
			if (state.type === "data") {
				const hasUI = getDataRenderer(dataRenderers, state.name, void 0) !== void 0;
				return {
					...state,
					dataRendererUI: hasUI ? /* @__PURE__ */ jsx(RegisteredDataRendererUI, {}) : null
				};
			}
			return state;
		} })
	});
};
const MessagePartChildren = (t0) => {
	const $ = c(5);
	const { index, children } = t0;
	let t1;
	if ($[0] !== children) {
		t1 = /* @__PURE__ */ jsx(MessagePartChildrenInner, { children });
		$[0] = children;
		$[1] = t1;
	} else t1 = $[1];
	let t2;
	if ($[2] !== index || $[3] !== t1) {
		t2 = /* @__PURE__ */ jsx(PartByIndexProvider, {
			index,
			children: t1
		});
		$[2] = index;
		$[3] = t1;
		$[4] = t2;
	} else t2 = $[4];
	return t2;
};
const MessagePrimitivePartsInner = (t0) => {
	const $ = c(11);
	const { children } = t0;
	const partKeys = useAuiState(useShallowSelector(_temp1));
	const contentLength = partKeys.length;
	const isRunning = useAuiState(_temp10);
	const isEmptyRunning = contentLength === 0 && isRunning;
	if (contentLength === 0) {
		if (!isEmptyRunning) return null;
		let t1;
		if ($[0] !== children) {
			t1 = children({ part: EMPTY_RUNNING_TEXT_PART });
			$[0] = children;
			$[1] = t1;
		} else t1 = $[1];
		let t2;
		if ($[2] !== t1) {
			t2 = /* @__PURE__ */ jsx(TextMessagePartProvider, {
				text: "",
				isRunning: true,
				children: t1
			});
			$[2] = t1;
			$[3] = t2;
		} else t2 = $[3];
		return t2;
	}
	let t1;
	if ($[4] !== children || $[5] !== partKeys) {
		let t2;
		if ($[7] !== children) {
			t2 = (key, index) => /* @__PURE__ */ jsx(MessagePartChildren, {
				index,
				children: (value) => children(value) ?? /* @__PURE__ */ jsx(DefaultPartFallback, {})
			}, key);
			$[7] = children;
			$[8] = t2;
		} else t2 = $[8];
		t1 = partKeys.map(t2);
		$[4] = children;
		$[5] = partKeys;
		$[6] = t1;
	} else t1 = $[6];
	let t2;
	if ($[9] !== t1) {
		t2 = /* @__PURE__ */ jsx(Fragment$1, { children: t1 });
		$[9] = t1;
		$[10] = t2;
	} else t2 = $[10];
	return t2;
};
/**
* Renders the parts of a message with support for multiple content types.
*
* This is the platform-agnostic base. Each platform wraps this with its own
* default components (web uses `<p>`, `<span>`; RN would use `<Text>`, etc.).
*/
const MessagePrimitiveParts = (t0) => {
	const $ = c(5);
	const { components, unstable_showEmptyOnNonTextEnd: t1, children } = t0;
	const unstable_showEmptyOnNonTextEnd = t1 === void 0 ? true : t1;
	if (children) {
		let t2;
		if ($[0] !== children) {
			t2 = /* @__PURE__ */ jsx(MessagePrimitivePartsInner, { children });
			$[0] = children;
			$[1] = t2;
		} else t2 = $[1];
		return t2;
	}
	let t2;
	if ($[2] !== components || $[3] !== unstable_showEmptyOnNonTextEnd) {
		t2 = /* @__PURE__ */ jsx(MessagePrimitivePartsCompat, {
			components,
			unstable_showEmptyOnNonTextEnd
		});
		$[2] = components;
		$[3] = unstable_showEmptyOnNonTextEnd;
		$[4] = t2;
	} else t2 = $[4];
	return t2;
};
MessagePrimitiveParts.displayName = "MessagePrimitive.Parts";
const MessagePrimitivePartsCompat = (t0) => {
	const $ = c(18);
	const { components, unstable_showEmptyOnNonTextEnd } = t0;
	const contentLength = useAuiState(_temp11);
	const useChainOfThought = !!components?.ChainOfThought;
	const { ranges: messageRanges, partIds } = useMessagePartsGroups(useChainOfThought);
	let t1;
	bb0: {
		if (contentLength === 0) {
			let t2;
			if ($[0] !== components) {
				t2 = /* @__PURE__ */ jsx(EmptyParts, { components });
				$[0] = components;
				$[1] = t2;
			} else t2 = $[1];
			t1 = t2;
			break bb0;
		}
		let t2;
		if ($[2] !== components || $[3] !== messageRanges || $[4] !== partIds) {
			let t3;
			if ($[6] !== components || $[7] !== partIds) {
				t3 = (range) => {
					if (range.type === "single") return /* @__PURE__ */ jsx(MessagePrimitivePartByIndex, {
						index: range.index,
						components
					}, partIds[range.index]);
					const groupKey = JSON.stringify([range.type, range.idKey ?? range.startIndex]);
					if (range.type === "chainOfThoughtGroup") {
						const ChainOfThoughtComponent = components?.ChainOfThought;
						if (!ChainOfThoughtComponent) return null;
						return /* @__PURE__ */ jsx(ChainOfThoughtByIndicesProvider, {
							startIndex: range.startIndex,
							endIndex: range.endIndex,
							children: /* @__PURE__ */ jsx(ChainOfThoughtComponent, {})
						}, groupKey);
					} else if (range.type === "toolGroup") {
						const ToolGroupComponent = components?.ToolGroup ?? defaultComponents.ToolGroup;
						return /* @__PURE__ */ jsx(ToolGroupComponent, {
							startIndex: range.startIndex,
							endIndex: range.endIndex,
							children: Array.from({ length: range.endIndex - range.startIndex + 1 }, (_, i) => {
								const partIndex = range.startIndex + i;
								return /* @__PURE__ */ jsx(MessagePrimitivePartByIndex, {
									index: partIndex,
									components
								}, partIds[partIndex]);
							})
						}, groupKey);
					} else {
						const ReasoningGroupComponent = components?.ReasoningGroup ?? defaultComponents.ReasoningGroup;
						return /* @__PURE__ */ jsx(ReasoningGroupComponent, {
							startIndex: range.startIndex,
							endIndex: range.endIndex,
							children: Array.from({ length: range.endIndex - range.startIndex + 1 }, (__0, i_0) => {
								const partIndex_0 = range.startIndex + i_0;
								return /* @__PURE__ */ jsx(MessagePrimitivePartByIndex, {
									index: partIndex_0,
									components
								}, partIds[partIndex_0]);
							})
						}, groupKey);
					}
				};
				$[6] = components;
				$[7] = partIds;
				$[8] = t3;
			} else t3 = $[8];
			t2 = messageRanges.map(t3);
			$[2] = components;
			$[3] = messageRanges;
			$[4] = partIds;
			$[5] = t2;
		} else t2 = $[5];
		t1 = t2;
	}
	const partsElements = t1;
	let t2;
	if ($[9] !== components) {
		t2 = components?.Quote && /* @__PURE__ */ jsx(QuoteRenderer, { Quote: components.Quote });
		$[9] = components;
		$[10] = t2;
	} else t2 = $[10];
	let t3;
	if ($[11] !== components || $[12] !== unstable_showEmptyOnNonTextEnd) {
		t3 = /* @__PURE__ */ jsx(ConditionalEmpty, {
			components,
			enabled: unstable_showEmptyOnNonTextEnd
		});
		$[11] = components;
		$[12] = unstable_showEmptyOnNonTextEnd;
		$[13] = t3;
	} else t3 = $[13];
	let t4;
	if ($[14] !== partsElements || $[15] !== t2 || $[16] !== t3) {
		t4 = /* @__PURE__ */ jsxs(Fragment$1, { children: [
			t2,
			partsElements,
			t3
		] });
		$[14] = partsElements;
		$[15] = t2;
		$[16] = t3;
		$[17] = t4;
	} else t4 = $[17];
	return t4;
};
function _temp(c) {
	return c.type;
}
function _temp2(s) {
	return s.message.parts.map(_temp);
}
function _temp3(s_0) {
	return getMessagePartKeys(s_0.message.parts);
}
function _temp4(s) {
	return s.part;
}
function _temp5(s) {
	return s.message.status ?? COMPLETE_STATUS;
}
function _temp6(s) {
	return s.part;
}
function _temp7(s_0) {
	return s_0.part.type === "tool-call" ? resolveToolRender(s_0.tools, s_0.part) : null;
}
function _temp8(s) {
	return s.part;
}
function _temp9(s_0) {
	return s_0.part.type === "data" ? getDataRenderer(s_0.dataRenderers, s_0.part.name, void 0) ?? null : null;
}
function _temp0(s) {
	return s.part.type;
}
function _temp1(s) {
	return getMessagePartKeys(s.message.parts);
}
function _temp10(s_0) {
	return (s_0.message.status?.type ?? "complete") === "running";
}
function _temp11(s) {
	return s.message.parts.length;
}
//#endregion
export { DefaultPartFallback, MessagePartChildren, MessagePartComponent, MessagePrimitivePartByIndex, MessagePrimitiveParts, defaultComponents, groupMessageParts };
