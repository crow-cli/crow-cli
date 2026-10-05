"use client";
import { PartByIndexProvider } from "../../context/providers/PartByIndexProvider.js";
import { TextMessagePartProvider } from "../../context/providers/TextMessagePartProvider.js";
import { MessagePartPrimitiveText } from "../messagePart/MessagePartText.js";
import { MessagePartPrimitiveImage } from "../messagePart/MessagePartImage.js";
import { MessagePartPrimitiveInProgress } from "../messagePart/MessagePartInProgress.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { memo } from "@assistant-ui/tap/react-shim";
import { useAui, useAuiState } from "@assistant-ui/store";
import { getMessagePartKeys } from "@assistant-ui/core/internal";
import { Fragment, jsx, jsxs } from "react/jsx-runtime";
//#region src/primitives/message/MessagePartsGrouped.tsx
/**
* Groups message parts by their parent ID.
* Parts without a parent ID appear in their chronological position as individual groups.
* Parts with the same parent ID are grouped together at the position of their first occurrence.
*/
const groupMessagePartsByParentId = (parts) => {
	const groupMap = /* @__PURE__ */ new Map();
	for (let i = 0; i < parts.length; i++) {
		const groupId = parts[i]?.parentId ?? i;
		const indices = groupMap.get(groupId) ?? [];
		indices.push(i);
		groupMap.set(groupId, indices);
	}
	const groups = [];
	for (const [groupId, indices] of groupMap) {
		const groupKey = typeof groupId === "string" ? groupId : void 0;
		groups.push({
			groupKey,
			indices
		});
	}
	return groups;
};
const useMessagePartsGrouped = (groupingFunction) => {
	const $ = c(9);
	const parts = useAuiState(_temp);
	let t0;
	bb0: {
		if (parts.length === 0) {
			let t1;
			if ($[0] === Symbol.for("react.memo_cache_sentinel")) {
				t1 = [];
				$[0] = t1;
			} else t1 = $[0];
			t0 = t1;
			break bb0;
		}
		let t1;
		if ($[1] !== groupingFunction || $[2] !== parts) {
			t1 = groupingFunction(parts);
			$[1] = groupingFunction;
			$[2] = parts;
			$[3] = t1;
		} else t1 = $[3];
		t0 = t1;
	}
	const groups = t0;
	let t1;
	if ($[4] !== parts) {
		t1 = getMessagePartKeys(parts);
		$[4] = parts;
		$[5] = t1;
	} else t1 = $[5];
	let t2;
	if ($[6] !== groups || $[7] !== t1) {
		t2 = {
			groups,
			partKeys: t1
		};
		$[6] = groups;
		$[7] = t1;
		$[8] = t2;
	} else t2 = $[8];
	return t2;
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
		t1 = (s) => {
			const named = s.dataRenderers.renderers[props.name]?.[0];
			if (named) return named;
			return s.dataRenderers.fallbacks[0] ?? Fallback;
		};
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
const defaultComponents = {
	Text: () => /* @__PURE__ */ jsxs("p", {
		style: { whiteSpace: "pre-line" },
		children: [/* @__PURE__ */ jsx(MessagePartPrimitiveText, {}), /* @__PURE__ */ jsx(MessagePartPrimitiveInProgress, { children: /* @__PURE__ */ jsx("span", {
			style: { fontFamily: "revert" },
			children: " ●"
		}) })]
	}),
	Reasoning: () => null,
	Source: () => null,
	Image: () => /* @__PURE__ */ jsx(MessagePartPrimitiveImage, {}),
	File: () => null,
	Unstable_Audio: () => null,
	Group: ({ children }) => children
};
const MessagePartComponent = (t0) => {
	const $ = c(50);
	const { components: t1 } = t0;
	let t2;
	if ($[0] !== t1) {
		t2 = t1 === void 0 ? {} : t1;
		$[0] = t1;
		$[1] = t2;
	} else t2 = $[1];
	const { Text: t3, Reasoning: t4, Image: t5, Source: t6, File: t7, Unstable_Audio: t8, tools: t9, data } = t2;
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
	const part = useAuiState(_temp2);
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
		default:
			console.warn(`Unknown message part type: ${type}`);
			return null;
	}
};
const MessagePartImpl = (t0) => {
	const $ = c(5);
	const { partIndex, components } = t0;
	let t1;
	if ($[0] !== components) {
		t1 = /* @__PURE__ */ jsx(MessagePartComponent, { components });
		$[0] = components;
		$[1] = t1;
	} else t1 = $[1];
	let t2;
	if ($[2] !== partIndex || $[3] !== t1) {
		t2 = /* @__PURE__ */ jsx(PartByIndexProvider, {
			index: partIndex,
			children: t1
		});
		$[2] = partIndex;
		$[3] = t1;
		$[4] = t2;
	} else t2 = $[4];
	return t2;
};
const MessagePart = memo(MessagePartImpl, (prev, next) => prev.partIndex === next.partIndex && prev.components?.Text === next.components?.Text && prev.components?.Reasoning === next.components?.Reasoning && prev.components?.Source === next.components?.Source && prev.components?.Image === next.components?.Image && prev.components?.File === next.components?.File && prev.components?.Unstable_Audio === next.components?.Unstable_Audio && prev.components?.tools === next.components?.tools && prev.components?.data === next.components?.data && prev.components?.Group === next.components?.Group);
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
const EmptyPartsImpl = (t0) => {
	const $ = c(6);
	const { components } = t0;
	const status = useAuiState(_temp3);
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
/**
* Renders the parts of a message grouped by a custom grouping function.
*
* This component allows you to group message parts based on any criteria you define.
* The grouping function receives all message parts and returns an array of groups,
* where each group has a key and an array of part indices.
*
* @deprecated Prefer `<MessagePrimitive.GroupedParts>` for adjacent
* grouping — it dispatches all rendering through one `switch (part.type)`
* and supports nested group paths. Keep this primitive only for
* non-adjacent clustering (e.g., gathering parts with the same parent-id
* across the message).
*
* @example
* ```tsx
* // Group by parent ID (default behavior)
* <MessagePrimitive.Unstable_PartsGrouped
*   components={{
*     Text: ({ text }) => <p className="message-text">{text}</p>,
*     Image: ({ image }) => <img src={image} alt="Message image" />,
*     Group: ({ groupKey, indices, children }) => {
*       if (!groupKey) return <>{children}</>;
*       return (
*         <div className="parent-group border rounded p-4">
*           <h4>Parent ID: {groupKey}</h4>
*           {children}
*         </div>
*       );
*     }
*   }}
* />
* ```
*/
const MessagePrimitiveUnstable_PartsGrouped = (t0) => {
	const $ = c(11);
	const { groupingFunction, components } = t0;
	const contentLength = useAuiState(_temp4);
	const { groups: messageGroups, partKeys } = useMessagePartsGrouped(groupingFunction);
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
		if ($[2] !== components || $[3] !== messageGroups || $[4] !== partKeys) {
			let t3;
			if ($[6] !== components || $[7] !== partKeys) {
				t3 = (group, groupIndex) => {
					const GroupComponent = components?.Group ?? defaultComponents.Group;
					const identity = partKeys[group.indices[0]];
					return /* @__PURE__ */ jsx(GroupComponent, {
						groupKey: group.groupKey,
						indices: group.indices,
						children: group.indices.map((partIndex) => /* @__PURE__ */ jsx(MessagePart, {
							partIndex,
							components
						}, partKeys[partIndex]))
					}, JSON.stringify([
						"group",
						group.groupKey ?? null,
						identity?.includes(":") ? `id:${identity}` : groupIndex
					]));
				};
				$[6] = components;
				$[7] = partKeys;
				$[8] = t3;
			} else t3 = $[8];
			t2 = messageGroups.map(t3);
			$[2] = components;
			$[3] = messageGroups;
			$[4] = partKeys;
			$[5] = t2;
		} else t2 = $[5];
		t1 = t2;
	}
	const partsElements = t1;
	let t2;
	if ($[9] !== partsElements) {
		t2 = /* @__PURE__ */ jsx(Fragment, { children: partsElements });
		$[9] = partsElements;
		$[10] = t2;
	} else t2 = $[10];
	return t2;
};
MessagePrimitiveUnstable_PartsGrouped.displayName = "MessagePrimitive.Unstable_PartsGrouped";
/**
* Renders the parts of a message grouped by their parent ID.
* This is a convenience wrapper around Unstable_PartsGrouped with parent ID grouping.
*
* @deprecated Use MessagePrimitive.Unstable_PartsGrouped instead for more flexibility
*/
const MessagePrimitiveUnstable_PartsGroupedByParentId = (t0) => {
	const $ = c(6);
	let components;
	let props;
	if ($[0] !== t0) {
		({components, ...props} = t0);
		$[0] = t0;
		$[1] = components;
		$[2] = props;
	} else {
		components = $[1];
		props = $[2];
	}
	let t1;
	if ($[3] !== components || $[4] !== props) {
		t1 = /* @__PURE__ */ jsx(MessagePrimitiveUnstable_PartsGrouped, {
			...props,
			components,
			groupingFunction: groupMessagePartsByParentId
		});
		$[3] = components;
		$[4] = props;
		$[5] = t1;
	} else t1 = $[5];
	return t1;
};
MessagePrimitiveUnstable_PartsGroupedByParentId.displayName = "MessagePrimitive.Unstable_PartsGroupedByParentId";
function _temp(s) {
	return s.message.parts;
}
function _temp2(s) {
	return s.part;
}
function _temp3(s) {
	return s.message.status ?? COMPLETE_STATUS;
}
function _temp4(s) {
	return s.message.parts.length;
}
//#endregion
export { MessagePrimitiveUnstable_PartsGrouped, MessagePrimitiveUnstable_PartsGroupedByParentId };
