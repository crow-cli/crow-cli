"use client";
import { getMessagePartKeys } from "../../../utils/getMessagePartKeys.js";
import { getGroupSummary } from "../../../utils/getGroupStatus.js";
import { DefaultPartFallback, MessagePartChildren } from "./MessageParts.js";
import { GROUPBY_MEMO_KEY, buildGroupTree } from "../../utils/groupParts.js";
import { Fragment, useMemo } from "@assistant-ui/tap/react-shim";
import { useAuiState } from "@assistant-ui/store";
import { useShallowSelector } from "@assistant-ui/store/internal";
import { Fragment as Fragment$1, jsx, jsxs } from "react/jsx-runtime";
//#region src/react/primitives/message/MessageGroupedParts.tsx
const shouldShowIndicator = (mode, parts, isRunning) => {
	if (!isRunning) return false;
	switch (mode) {
		case "never": return false;
		case "always": return true;
		case "empty": return parts.length === 0;
		case "no-text": {
			const last = parts[parts.length - 1];
			return last === void 0 || last.type !== "text" && last.type !== "reasoning";
		}
	}
};
/**
* `children` placeholder passed for leaf-part renders. Leaf parts have no
* inner subtree; rendering this sentinel signals the consumer wrote
* `default: return children;` and accidentally fell through for a part —
* surface the bug loudly instead of silently rendering nothing.
*/
const PartChildrenSentinel = () => {
	throw new Error("MessagePrimitive.GroupedParts: rendered `children` under a leaf part. `children` is only meaningful for `group-…` cases — add a matching case for the part type or return `null` to use registered UIs.");
};
const renderNode = (node, parts, render) => {
	if (node.type === "part") return /* @__PURE__ */ jsx(MessagePartChildren, {
		index: node.index,
		children: ({ part }) => render({
			part,
			children: /* @__PURE__ */ jsx(PartChildrenSentinel, {})
		}) ?? /* @__PURE__ */ jsx(DefaultPartFallback, {})
	}, node.idKey ? `part-${node.idKey}` : `part-${node.index}`);
	const { status, counts } = getGroupSummary(parts, node.indices);
	const groupPart = {
		type: node.key,
		status,
		counts,
		indices: node.indices
	};
	return /* @__PURE__ */ jsx(Fragment, { children: render({
		part: groupPart,
		children: /* @__PURE__ */ jsx(Fragment$1, { children: node.children.map((child) => renderNode(child, parts, render)) })
	}) }, JSON.stringify([node.key, node.idKey ?? node.nodeKey]));
};
/**
* Groups adjacent message parts into a tree of coalesced runs and
* renders each node — group or part — through a single `children`
* function.
*
* The render function receives `{ part, children }` where `part.type`
* is either a `"group-…"` literal (for a group, `children` is the
* recursively-rendered subtree) or a real part type (`"text"`,
* `"tool-call"`, …) for a leaf (`children` is a sentinel that throws
* if rendered — use `part.type` to distinguish).
*
* @example
* ```tsx
* <MessagePrimitive.GroupedParts
*   groupBy={groupPartByType({
*     reasoning: ["group-thought", "group-reasoning"],
*     "tool-call": ["group-thought", "group-tool"],
*   })}
* >
*   {({ part, children }) => {
*     switch (part.type) {
*       case "group-thought":   return <Thought>{children}</Thought>;
*       case "group-reasoning": return <Reasoning>{children}</Reasoning>;
*       case "group-tool":      return <ToolStack>{children}</ToolStack>;
*       case "text":            return <MarkdownText />;
*       case "tool-call":       return part.toolUI ?? <ToolFallback {...part} />;
*       case "indicator":       return <LoadingDots />;
*       default:                return null;
*     }
*   }}
* </MessagePrimitive.GroupedParts>
* ```
*/
const MessagePrimitiveGroupedParts = ({ groupBy, indicator = "no-text", children }) => {
	const parts = useAuiState(useShallowSelector((s) => s.message.parts));
	const toolUIs = useAuiState((s_0) => s_0.tools.toolUIs);
	const isRunning = useAuiState((s_1) => indicator === "never" ? false : s_1.message.status?.type === "running");
	const memoDep = groupBy[GROUPBY_MEMO_KEY] ?? groupBy;
	const tree = useMemo(() => {
		const context = { toolUIs };
		return buildGroupTree(parts.map((part) => groupBy(part, context) ?? []), getMessagePartKeys(parts));
	}, [
		parts,
		memoDep,
		toolUIs
	]);
	return /* @__PURE__ */ jsxs(Fragment$1, { children: [tree.map((node) => renderNode(node, parts, children)), shouldShowIndicator(indicator, parts, isRunning) && children({
		part: { type: "indicator" },
		children: /* @__PURE__ */ jsx(PartChildrenSentinel, {})
	})] });
};
MessagePrimitiveGroupedParts.displayName = "MessagePrimitive.GroupedParts";
//#endregion
export { MessagePrimitiveGroupedParts };
