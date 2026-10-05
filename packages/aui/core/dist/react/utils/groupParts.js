import { isMcpAppUri } from "../../types/message.js";
//#region src/react/utils/groupParts.ts
/**
* Hierarchical adjacent-coalescing grouping for message parts.
*
* Given a group path per part (from `groupBy`), builds a tree of group
* nodes wrapping individual parts. Adjacent parts sharing a path prefix
* coalesce into the same group; ungrouped parts are direct children of
* the root.
*
* Each node gets a structural `nodeKey` built from sibling indices
* (`"0.1.0"`), stable under append-only streaming.
*/
/**
* Symbol attached to memoizable `groupBy` functions (e.g. those returned
* by {@link groupPartByType}). Carries a string fingerprint of the config
* so `MessagePrimitive.GroupedParts` can memo the tree on
* `[parts, memoKey]` across renders — even when the helper call site
* reconstructs the function each render.
*/
const GROUPBY_MEMO_KEY = Symbol.for("@assistant-ui/groupBy.memoKey");
/**
* Build a `groupBy` from a `part.type → group-key path` lookup.
* Parts whose type isn't in the map are left ungrouped. The returned
* function carries a stable {@link GROUPBY_MEMO_KEY} fingerprint so
* `<MessagePrimitive.GroupedParts>` can memoize its tree across renders.
*
* The synthetic `"standalone-tool-call"` key matches tool calls that should
* render outside the chain-of-thought grouping. MCP-app calls are detected from
* the part alone; the registry-driven cases (human tools, the generative-UI
* tool, `display: "standalone"` opt-ins) are resolved from the
* {@link GroupByContext} that `<MessagePrimitive.GroupedParts>` passes to the
* `groupBy` function — the helper needs nothing threaded into it.
*
* A `"tool-call:<name>"` entry matches tool calls by tool name and takes precedence over the plain `"tool-call"` entry, while `"standalone-tool-call"` still wins first.
*
* @example
* ```tsx
* <MessagePrimitive.GroupedParts
*   groupBy={groupPartByType({
*     reasoning: ["group-thought", "group-reasoning"],
*     "tool-call:task": ["group-subagents"],
*     "tool-call": ["group-thought", "group-tool"],
*     "standalone-tool-call": [],
*   })}
* >
*   {({ part, children }) => { ... }}
* </MessagePrimitive.GroupedParts>
* ```
*/
const groupPartByType = (map) => {
	const lookup = map;
	const fn = ((part, context) => {
		if (part.type === "tool-call") {
			if ((isMcpAppUri(part.mcp?.app?.resourceUri) || (context?.toolUIs?.[part.toolName]?.[0]?.standalone ?? false)) && lookup["standalone-tool-call"] !== void 0) return lookup["standalone-tool-call"];
			const toolCallPath = lookup[`tool-call:${part.toolName}`];
			if (toolCallPath !== void 0) return toolCallPath;
			return lookup["tool-call"] ?? [];
		}
		return lookup[part.type] ?? [];
	});
	const sortedEntries = Object.keys(map).sort().map((k) => [k, map[k]]);
	fn[GROUPBY_MEMO_KEY] = `groupPartByType:${JSON.stringify(sortedEntries)}`;
	return fn;
};
const makeChildNodeKey = (parent) => {
	const idx = parent.nextChildIdx++;
	return parent.nodeKey === "" ? String(idx) : `${parent.nodeKey}.${idx}`;
};
const claimIdKey = (frame, id) => {
	if (id === void 0 || frame.claimed.has(id)) return void 0;
	frame.claimed.add(id);
	return `id:${id}`;
};
/**
* Build the group tree from an array of normalized group paths.
* `paths[i]` is the path for part `i`. The output tree contains one
* `part` node per part and one `group` node per coalesced run.
*/
const buildGroupTree = (paths, partIds) => {
	const root = {
		key: "",
		nodeKey: "",
		indices: [],
		children: [],
		nextChildIdx: 0,
		claimed: /* @__PURE__ */ new Set()
	};
	const stack = [root];
	const closeTop = () => {
		const closing = stack.pop();
		const parent = stack[stack.length - 1];
		const id = partIds?.[closing.indices[0]];
		parent.children.push({
			type: "group",
			key: closing.key,
			nodeKey: closing.nodeKey,
			idKey: claimIdKey(parent, id?.includes(":") ? id : void 0),
			indices: closing.indices,
			children: closing.children
		});
	};
	for (let i = 0; i < paths.length; i++) {
		const path = paths[i];
		let common = 0;
		while (common < stack.length - 1 && common < path.length && stack[common + 1].key === path[common]) common++;
		while (stack.length - 1 > common) closeTop();
		while (stack.length - 1 < path.length) {
			const parent = stack[stack.length - 1];
			stack.push({
				key: path[stack.length - 1],
				nodeKey: makeChildNodeKey(parent),
				indices: [],
				children: [],
				nextChildIdx: 0,
				claimed: /* @__PURE__ */ new Set()
			});
		}
		const top = stack[stack.length - 1];
		top.children.push({
			type: "part",
			index: i,
			nodeKey: makeChildNodeKey(top),
			idKey: claimIdKey(top, partIds?.[i])
		});
		for (let s = 1; s < stack.length; s++) stack[s].indices.push(i);
	}
	while (stack.length > 1) closeTop();
	return root.children;
};
//#endregion
export { GROUPBY_MEMO_KEY, buildGroupTree, groupPartByType };
