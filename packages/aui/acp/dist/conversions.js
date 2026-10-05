"use client";
import { isRecord, parseDataUrl, resolveFilePartSource } from "@assistant-ui/core/internal";
//#region src/conversions.ts
const isSettled = (status) => status === "completed" || status === "failed";
function threadContentToAcpBlocks(content) {
	const blocks = [];
	for (const part of content) switch (part.type) {
		case "text":
			if (part.text) blocks.push({
				type: "text",
				text: part.text
			});
			break;
		case "image": {
			if (!part.image) break;
			const parsed = parseDataUrl(part.image);
			blocks.push(parsed ? {
				type: "image",
				data: parsed.data,
				mimeType: parsed.mimeType
			} : {
				type: "resource_link",
				uri: part.image,
				name: part.filename || part.image
			});
			break;
		}
		case "audio": {
			const data = part.audio?.data;
			if (!data) break;
			blocks.push({
				type: "audio",
				data,
				mimeType: `audio/${part.audio?.format ?? "mp3"}`
			});
			break;
		}
		case "file": {
			const source = resolveFilePartSource(part);
			if (source.kind === "url") {
				blocks.push({
					type: "resource_link",
					uri: source.url,
					name: part.filename || source.url,
					...part.mimeType ? { mimeType: part.mimeType } : void 0
				});
				break;
			}
			const mimeType = source.mimeType || part.mimeType || "application/octet-stream";
			if (mimeType.startsWith("image/")) {
				blocks.push({
					type: "image",
					data: source.data,
					mimeType
				});
				break;
			}
			if (mimeType.startsWith("audio/")) {
				blocks.push({
					type: "audio",
					data: source.data,
					mimeType
				});
				break;
			}
			blocks.push({
				type: "resource",
				resource: {
					uri: `file:///${part.filename ?? "attachment"}`,
					mimeType,
					blob: source.data
				}
			});
			break;
		}
	}
	return blocks;
}
const resourceLinkOf = (block) => ({
	type: "resource_link",
	uri: block.resource.uri,
	name: block.resource.uri,
	...block.resource.mimeType ? { mimeType: block.resource.mimeType } : void 0
});
/** A `file:` URI names a client-local file, which the agent cannot fetch. */
const isAgentRetrievable = (uri) => !/^file:/i.test(uri);
/**
* Text and resource links are the ACP baseline; every other block type has to
* be opted into through `promptCapabilities`. An embedded resource the agent
* cannot accept keeps whatever survives: its text travels as text, and a URI
* the agent can fetch travels as a resource link. Inline bytes behind a
* client-local URI survive neither way and are withheld like any other block
* the agent cannot accept.
*/
function filterPromptBlocks(blocks, capabilities) {
	const kept = [];
	const dropped = [];
	for (const block of blocks) switch (block.type) {
		case "image":
			(capabilities?.image ? kept : dropped).push(block);
			break;
		case "audio":
			(capabilities?.audio ? kept : dropped).push(block);
			break;
		case "resource": {
			if (capabilities?.embeddedContext) {
				kept.push(block);
				break;
			}
			const text = "text" in block.resource ? block.resource.text : void 0;
			if (text !== void 0) kept.push({
				type: "text",
				text
			});
			else if (isAgentRetrievable(block.resource.uri)) kept.push(resourceLinkOf(block));
			else dropped.push(block);
			break;
		}
		default: kept.push(block);
	}
	return {
		blocks: kept,
		dropped
	};
}
const blockToText = (block) => {
	switch (block.type) {
		case "text": return block.text;
		case "resource": return "text" in block.resource ? block.resource.text : void 0;
		case "resource_link": return `[${block.name}](${block.uri})`;
		default: return;
	}
};
const asBlockArray = (raw) => {
	if (Array.isArray(raw)) return raw;
	if (raw && typeof raw === "object") return [raw];
	return [];
};
function toolCallContentToText(content) {
	if (!content || content.length === 0) return void 0;
	const pieces = [];
	for (const item of content) if (item.type === "content") for (const block of asBlockArray(item.content)) {
		const text = blockToText(block);
		if (text) pieces.push(text);
	}
	else if (item.type === "diff") pieces.push(`--- ${item.path}\n+++ ${item.path}\n${item.newText}`);
	return pieces.length > 0 ? pieces.join("\n") : void 0;
}
function stopReasonToMessageStatus(stopReason) {
	switch (stopReason) {
		case "cancelled": return {
			type: "incomplete",
			reason: "cancelled"
		};
		case "max_tokens": return {
			type: "incomplete",
			reason: "length"
		};
		case "refusal":
		case "max_turn_requests": return {
			type: "incomplete",
			reason: "other"
		};
		default: return {
			type: "complete",
			reason: "stop"
		};
	}
}
const PERMISSION_KIND_TO_APPROVAL_KIND = {
	allow_once: "allow-once",
	allow_always: "allow-always",
	reject_once: "reject-once",
	reject_always: "reject-always"
};
function permissionOptionToApprovalOption(option) {
	return {
		id: option.optionId,
		kind: PERMISSION_KIND_TO_APPROVAL_KIND[option.kind] ?? option.kind,
		label: option.name
	};
}
function isAllowKind(kind) {
	return kind === "allow_once" || kind === "allow_always";
}
function isRejectKind(kind) {
	return kind === "reject_once" || kind === "reject_always";
}
/**
* An explicit `optionId` wins; otherwise the decision picks the first option
* of the matching family. Never cross families — the agent supplies `options`,
* so an `options[0]` fallback could turn a denial into a grant.
*/
function resolvePermissionOutcome(request, decision) {
	const matchesFamily = decision.approved ? isAllowKind : isRejectKind;
	const chosen = (decision.optionId ? request.options.find((o) => o.optionId === decision.optionId) : void 0) ?? request.options.find((o) => matchesFamily(o.kind));
	return chosen ? {
		outcome: "selected",
		optionId: chosen.optionId
	} : { outcome: "cancelled" };
}
const safeStringify = (value) => {
	try {
		return JSON.stringify(value) ?? "";
	} catch {
		return String(value);
	}
};
/** Namespace this package uses on a part's `providerMetadata`. */
const ACP_METADATA_NAMESPACE = "acp";
const metadataOf = (part) => part.providerMetadata?.[ACP_METADATA_NAMESPACE];
/**
* A `tool_call_update` carries only what changed: omitting `name`, `kind`,
* `title` or `content` — or sending `null` — leaves the existing value in
* place, so a later frame must not drop one an earlier frame reported.
*/
const mergedMetadataOf = (update, previous) => {
	const metadata = {};
	const name = update.name ?? previous?.name;
	const kind = update.kind ?? previous?.kind;
	const title = update.title ?? previous?.title;
	const content = update.content ?? previous?.content;
	if (name !== void 0) metadata.name = name;
	if (kind !== void 0) metadata.kind = kind;
	if (title !== void 0) metadata.title = title;
	if (content !== void 0) metadata.content = content;
	return metadata;
};
const sameMetadata = (metadata, previous) => metadata.name === previous?.name && metadata.kind === previous?.kind && metadata.title === previous?.title && metadata.content === previous?.content;
/**
* `toolName` is the key apps register tool UIs against, so it has to stay
* stable for the life of a call: the protocol's programmatic `name` first,
* then the `kind` enum, and only then the human-readable `title`.
*/
const toolNameOf = (metadata) => {
	return metadata.name || metadata.kind || metadata.title || void 0;
};
const settledResult = (update, previous) => {
	if (update.rawOutput !== void 0) return update.rawOutput;
	if (update.content != null) return toolCallContentToText(update.content) ?? previous.result ?? null;
	return previous.result ?? null;
};
function buildToolCallPart(update, knownStatus) {
	const args = isRecord(update.rawInput) ? update.rawInput : {};
	const status = update.status ?? knownStatus ?? "pending";
	const metadata = mergedMetadataOf(update, void 0);
	const part = {
		type: "tool-call",
		toolCallId: update.toolCallId,
		toolName: toolNameOf(metadata) ?? "tool_call",
		args,
		argsText: update.rawInput !== void 0 ? safeStringify(update.rawInput) : "",
		...Object.keys(metadata).length > 0 && { providerMetadata: { [ACP_METADATA_NAMESPACE]: metadata } }
	};
	if (!isSettled(status)) {
		if (update.rawOutput === void 0) return part;
		return {
			...part,
			result: update.rawOutput,
			isPreliminary: true
		};
	}
	return {
		...part,
		result: settledResult(update, part),
		isError: status === "failed"
	};
}
function mergeToolCallPart(existing, update, knownStatus) {
	let next = existing;
	const set = (patch) => {
		next = {
			...next,
			...patch
		};
	};
	const previous = metadataOf(existing);
	const metadata = mergedMetadataOf(update, previous);
	const toolName = toolNameOf(metadata);
	if (toolName && toolName !== next.toolName) set({ toolName });
	if (!sameMetadata(metadata, previous)) set({ providerMetadata: {
		...next.providerMetadata,
		[ACP_METADATA_NAMESPACE]: metadata
	} });
	if (update.rawInput !== void 0) {
		const argsText = safeStringify(update.rawInput);
		if (argsText !== next.argsText) set({
			args: isRecord(update.rawInput) ? update.rawInput : {},
			argsText
		});
	}
	const status = update.status ?? knownStatus ?? "pending";
	if (isSettled(status)) {
		const result = settledResult(update, next);
		const isError = status === "failed";
		if (result !== next.result || isError !== (next.isError ?? false) || next.isPreliminary) set({
			result,
			isError,
			...next.isPreliminary ? { isPreliminary: false } : void 0
		});
		return next;
	}
	if (update.rawOutput !== void 0) {
		if (update.rawOutput !== next.result) set({
			result: update.rawOutput,
			isPreliminary: true
		});
		return next;
	}
	if (update.content != null) {
		const text = toolCallContentToText(update.content);
		if (text !== void 0 && text !== next.result) set({
			result: text,
			isPreliminary: true
		});
	}
	return next;
}
const findToolCallIndex = (content, toolCallId) => {
	for (let i = 0; i < content.length; i++) {
		const part = content[i];
		if (part.type === "tool-call" && part.toolCallId === toolCallId) return i;
	}
	return -1;
};
const replaceAt = (content, index, part) => {
	const next = content.slice();
	next[index] = part;
	return next;
};
function applyToolCallUpdate(content, update, knownStatus) {
	const index = findToolCallIndex(content, update.toolCallId);
	if (index === -1) return [...content, buildToolCallPart(update, knownStatus)];
	const existing = content[index];
	const merged = mergeToolCallPart(existing, update, knownStatus);
	return merged === existing ? void 0 : replaceAt(content, index, merged);
}
function attachToolCallApproval(content, update, approval) {
	const index = findToolCallIndex(content, update.toolCallId);
	if (index === -1) return [...content, {
		...buildToolCallPart(update),
		approval
	}];
	const existing = content[index];
	return replaceAt(content, index, {
		...existing,
		approval
	});
}
function resolveToolCallApproval(content, approvalId, resolution) {
	for (let i = 0; i < content.length; i++) {
		const part = content[i];
		if (part.type !== "tool-call" || part.approval?.id !== approvalId) continue;
		return replaceAt(content, i, {
			...part,
			approval: {
				...part.approval,
				...resolution
			}
		});
	}
}
const mediaPartsFromBlock = (block) => {
	switch (block.type) {
		case "text": return block.text ? [{
			type: "text",
			text: block.text
		}] : [];
		case "image": return [{
			type: "image",
			image: `data:${block.mimeType};base64,${block.data}`
		}];
		case "audio": return [{
			type: "file",
			data: block.data,
			mimeType: block.mimeType
		}];
		case "resource_link": return [{
			type: "file",
			data: block.uri,
			mimeType: block.mimeType || "application/octet-stream",
			sourceType: "url",
			filename: block.name
		}];
		case "resource": {
			const resource = block.resource;
			if ("text" in resource) return resource.text ? [{
				type: "text",
				text: resource.text
			}] : [];
			const mimeType = resource.mimeType || "application/octet-stream";
			if (mimeType.startsWith("image/")) return [{
				type: "image",
				image: `data:${mimeType};base64,${resource.blob}`
			}];
			return [{
				type: "file",
				data: resource.blob,
				mimeType
			}];
		}
		default: return [];
	}
};
/**
* A content block as user-message parts. A `session/load` replay spells the
* user's own turns as `user_message_chunk`, and those carry the same blocks a
* prompt does — text, image, resource — so the mapping is the media one.
*/
function userPartsFromBlock(block) {
	return mediaPartsFromBlock(block);
}
const messagePartsFromBlock = (block, kind) => {
	if (kind === "text") return mediaPartsFromBlock(block);
	if (block.type === "text") return block.text ? [{
		type: "reasoning",
		text: block.text
	}] : [];
	if (block.type === "resource" && "text" in block.resource) return block.resource.text ? [{
		type: "reasoning",
		text: block.resource.text
	}] : [];
	return mediaPartsFromBlock(block);
};
function appendContentBlock(content, block, kind) {
	const parts = messagePartsFromBlock(block, kind);
	if (parts.length === 0) return void 0;
	if (parts.length === 1 && parts[0].type === kind) {
		const text = parts[0].text;
		const last = content[content.length - 1];
		if (last && last.type === kind) return replaceAt(content, content.length - 1, {
			...last,
			text: last.text + text
		});
	}
	return [...content, ...parts];
}
function applySessionUpdateToContent(content, update, knownStatus) {
	switch (update.sessionUpdate) {
		case "agent_message_chunk": return update.content ? appendContentBlock(content, update.content, "text") : void 0;
		case "agent_thought_chunk": return update.content ? appendContentBlock(content, update.content, "reasoning") : void 0;
		case "tool_call":
		case "tool_call_update": return typeof update.toolCallId === "string" ? applyToolCallUpdate(content, update, knownStatus) : void 0;
		default: return;
	}
}
//#endregion
export { appendContentBlock, applySessionUpdateToContent, applyToolCallUpdate, attachToolCallApproval, buildToolCallPart, filterPromptBlocks, isAllowKind, isRejectKind, mergeToolCallPart, permissionOptionToApprovalOption, resolvePermissionOutcome, resolveToolCallApproval, stopReasonToMessageStatus, threadContentToAcpBlocks, toolCallContentToText, userPartsFromBlock };
