//#region src/runtime/utils/tool-call-tree.ts
/**
* Walk every tool-call part reachable from `messages`. A tool call projects a
* child run as nested messages on `ToolCallMessagePart.messages`, so a
* subagent's own calls live below the top-level content and a seam that only
* scans the top level cannot reach them.
*
* Parts arrive in document order, each one ahead of its own descendants.
* `messageId` names the message that directly holds the part, which for a
* nested call is the child run's message rather than the top-level message the
* tree hangs from. Only assistant messages are descended, the same rule
* {@link mapToolCallPartsDeep} rewrites under, so a part this reports is always
* a part that can be written back.
*/
function* walkToolCallTree(messages) {
	for (const message of messages) {
		if (message?.role !== "assistant" || !Array.isArray(message.content)) continue;
		for (const part of message.content) {
			if (!part || part.type !== "tool-call") continue;
			yield {
				part,
				messageId: message.id
			};
			if (part.messages?.length) yield* walkToolCallTree(part.messages);
		}
	}
}
/**
* Content-level form of {@link walkToolCallTree}, for a caller that already
* holds one assistant message's content and does not need the owning id.
*/
function* iterateToolCallParts(content) {
	for (const part of content) {
		if (!part || part.type !== "tool-call") continue;
		yield part;
		if (part.messages?.length) for (const entry of walkToolCallTree(part.messages)) yield entry.part;
	}
}
/**
* Rebuild `content` with `fn` applied to every tool-call part in the tree.
* Arrays and nested messages are reused wherever `fn` returned the part it was
* given, so an unchanged subtree keeps its identity and `changed` reports
* whether anything moved.
*/
function mapToolCallPartsDeep(content, fn) {
	let changed = false;
	const next = content.map((part) => {
		if (part.type !== "tool-call") return part;
		let mapped = fn(part);
		if (mapped.messages !== void 0) {
			let nestedChanged = false;
			const nestedMessages = mapped.messages.map((nested) => {
				if (nested.role !== "assistant" || !Array.isArray(nested.content)) return nested;
				const assistant = nested;
				const result = mapToolCallPartsDeep(assistant.content, fn);
				if (!result.changed) return nested;
				nestedChanged = true;
				return {
					...assistant,
					content: result.content
				};
			});
			if (nestedChanged) mapped = mapped === part ? {
				...part,
				messages: nestedMessages
			} : {
				...mapped,
				messages: nestedMessages
			};
		}
		if (mapped !== part) changed = true;
		return mapped;
	});
	return changed ? {
		content: next,
		changed
	} : {
		content,
		changed
	};
}
//#endregion
export { iterateToolCallParts, mapToolCallPartsDeep, walkToolCallTree };
