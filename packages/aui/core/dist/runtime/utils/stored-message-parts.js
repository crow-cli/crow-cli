import { isJSONValue, isRecord } from "../../utils/json/is-json.js";
//#region src/runtime/utils/stored-message-parts.ts
const MAX_STORED_MESSAGE_DEPTH = 100;
const parseStoredDate = (value) => {
	if (value instanceof Date && !Number.isNaN(value.getTime())) return value;
	if (typeof value !== "string" && typeof value !== "number") return null;
	const date = new Date(value);
	return Number.isNaN(date.getTime()) ? null : date;
};
const isStoredMessageRole = (value) => value === "system" || value === "user" || value === "assistant";
const storedMessageStatusGuardsByType = {
	running: () => true,
	"requires-action": (status) => typeof status.reason === "string",
	complete: (status) => typeof status.reason === "string",
	incomplete: (status) => (status.reason === void 0 || typeof status.reason === "string") && (status.error === void 0 || isJSONValue(status.error))
};
const isStoredMessageStatus = (value) => isRecord(value) && typeof value.type === "string" && Object.hasOwn(storedMessageStatusGuardsByType, value.type) && storedMessageStatusGuardsByType[value.type](value) === true;
const parseStoredThreadStep = (value) => {
	if (!isRecord(value)) return void 0;
	if (value.messageId !== void 0 && typeof value.messageId !== "string") {
		const { messageId: _, ...step } = value;
		return parseStoredThreadStep(step);
	}
	if (value.usage !== void 0 && !isRecord(value.usage)) {
		const { usage: _, ...step } = value;
		return step;
	}
	return value;
};
const parseStoredThreadSteps = (value) => Array.isArray(value) ? value.map(parseStoredThreadStep).filter((step) => step !== void 0) : [];
/**
* Builds the readability predicate for a persistence boundary. A stored part is
* readable when it passes the guard for its known type, or when its type is
* unknown and the boundary can still read it.
*
* Unknown types are where the boundaries part: local storage hands its rows to
* the runtime untouched, so a type written by a newer release still loads,
* while the aui/v0 decoder converts a `data-` prefix and throws on anything
* else unknown. Per-type differences ride in `overrides`.
*/
const makeIsStoredMessagePart = (overrides, isReadableUnknownType) => {
	const guards = {
		text: (part) => typeof part.text === "string",
		reasoning: (part) => typeof part.text === "string" || typeof part.unstable_summary === "string",
		image: (part) => typeof part.image === "string",
		file: (part) => typeof part.data === "string" && typeof part.mimeType === "string",
		audio: (part) => isRecord(part.audio) && typeof part.audio.data === "string" && typeof part.audio.format === "string",
		data: (part) => typeof part.name === "string",
		source: (part) => typeof part.id === "string" && (part.sourceType === "url" ? typeof part.url === "string" : part.sourceType === "document" && typeof part.title === "string" && typeof part.mediaType === "string"),
		"generative-ui": (part) => isRecord(part.spec),
		"tool-call": (part) => typeof part.toolCallId === "string" && typeof part.toolName === "string" && isRecord(part.args) && typeof part.argsText === "string",
		...overrides
	};
	return (value) => isRecord(value) && typeof value.type === "string" && (Object.hasOwn(guards, value.type) ? guards[value.type](value) : isReadableUnknownType(value.type));
};
const isStoredMessagePart = makeIsStoredMessagePart({}, () => true);
/**
* The aui/v0 decoder dereferences each present field rather than reading only
* the one it needs, so this boundary checks every field it will touch, while
* local storage stays no stricter than what the runtime itself writes.
*/
const isStoredAuiV0Part = makeIsStoredMessagePart({
	reasoning: (part) => (part.text === void 0 || typeof part.text === "string") && (part.unstable_summary === void 0 || typeof part.unstable_summary === "string") && (typeof part.text === "string" || typeof part.unstable_summary === "string"),
	"tool-call": (part) => typeof part.toolCallId === "string" && typeof part.toolName === "string" && (part.args === void 0 || isRecord(part.args)) && (part.argsText === void 0 || typeof part.argsText === "string") && (part.args !== void 0 || part.argsText !== void 0)
}, (type) => type.startsWith("data-"));
const rolePartTypes = {
	user: {
		text: true,
		image: true,
		file: true,
		data: true,
		audio: true
	},
	assistant: {
		text: true,
		reasoning: true,
		"tool-call": true,
		source: true,
		file: true,
		image: true,
		data: true,
		"generative-ui": true
	}
};
/**
* `fromThreadMessageLike` converts each part through its role's branch and
* throws on a part that branch does not carry, which would cost the whole
* stored row. The aui/v0 boundary decodes through that converter, so it filters
* by role as well as by shape. A part type unknown to this table is left to the
* boundary predicate, which keeps the `data-` prefixes the converter handles.
*/
const isStoredAuiV0RolePart = (role, value) => isStoredAuiV0Part(value) && (role === "system" ? value.type === "text" : Object.hasOwn(rolePartTypes.assistant, value.type) || Object.hasOwn(rolePartTypes.user, value.type) ? Object.hasOwn(rolePartTypes[role], value.type) : true);
const parseStoredAttachment = (value, isPart) => {
	if (!isRecord(value) || typeof value.id !== "string" || typeof value.type !== "string" || typeof value.name !== "string" || !isRecord(value.status) || value.status.type !== "complete" || !Array.isArray(value.content)) return null;
	return {
		...value,
		content: value.content.filter(isPart)
	};
};
//#endregion
export { MAX_STORED_MESSAGE_DEPTH, isStoredAuiV0RolePart, isStoredMessagePart, isStoredMessageRole, isStoredMessageStatus, parseStoredAttachment, parseStoredDate, parseStoredThreadSteps };
