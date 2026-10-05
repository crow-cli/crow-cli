import { generateId } from "../../utils/id.js";
import { parseDataUrl } from "../../utils/data-url.js";
import { readToolInteractionLog } from "./tool-interactions.js";
import { parsePartialJsonObject } from "assistant-stream/utils";
//#region src/runtime/utils/thread-message-like.ts
const convertDataPrefixedPart = (type, data, id) => {
	if (!type.startsWith("data-")) return void 0;
	return {
		type: "data",
		name: type.substring(5),
		data,
		...typeof id === "string" && { id }
	};
};
/**
* @deprecated This API is experimental and may change without notice.
*/
const fromThreadMessageLike = (like, fallbackId, fallbackStatus) => {
	const { role, id, createdAt, attachments, status, metadata } = like;
	const common = {
		id: id ?? fallbackId,
		createdAt: createdAt ?? /* @__PURE__ */ new Date()
	};
	const content = typeof like.content === "string" ? [{
		type: "text",
		text: like.content
	}] : like.content;
	const sanitizeImageContent = ({ image, ...rest }) => {
		if (typeof image !== "string") return null;
		if (parseDataUrl(image)?.mimeType.startsWith("image/")) return {
			...rest,
			image
		};
		if (/^(https:\/\/|blob:)/i.test(image)) return {
			...rest,
			image
		};
		console.warn(`Invalid image data format detected`);
		return null;
	};
	if (role !== "user" && attachments?.length) throw new Error("attachments are only supported for user messages");
	if (role !== "assistant" && status) throw new Error("status is only supported for assistant messages");
	if (role !== "assistant" && metadata?.steps) throw new Error("metadata.steps is only supported for assistant messages");
	switch (role) {
		case "assistant": return {
			...common,
			role,
			content: content.map((part) => {
				const type = part.type;
				switch (type) {
					case "text":
						if (!part.text?.trim()) return null;
						return part;
					case "reasoning":
						if (!part.text?.trim() && !part.unstable_summary?.trim()) return null;
						return part;
					case "file":
					case "source": return part;
					case "image": return sanitizeImageContent(part);
					case "data": return part;
					case "generative-ui": return part;
					case "tool-call": {
						const { parentId, messages, unstable_interactions, ...basePart } = part;
						const interactions = readToolInteractionLog(unstable_interactions);
						const commonProps = {
							...basePart,
							toolCallId: part.toolCallId || `tool-${generateId()}`,
							...parentId !== void 0 && { parentId },
							...messages !== void 0 && { messages },
							...interactions !== void 0 && { unstable_interactions: interactions }
						};
						if (part.args) return {
							...commonProps,
							args: part.args,
							argsText: part.argsText ?? JSON.stringify(part.args)
						};
						return {
							...commonProps,
							args: parsePartialJsonObject(part.argsText ?? "") ?? {},
							argsText: part.argsText ?? ""
						};
					}
					case "audio": throw new Error(`Unsupported assistant message part type: ${type}`);
					default: {
						const dataType = type;
						const converted = convertDataPrefixedPart(dataType, part.data, part.id);
						if (converted) return converted;
						throw new Error(`Unsupported assistant message part type: ${dataType}`);
					}
				}
			}).filter((c) => !!c),
			status: status ?? fallbackStatus,
			metadata: {
				unstable_state: metadata?.unstable_state ?? null,
				unstable_annotations: metadata?.unstable_annotations ?? [],
				unstable_data: metadata?.unstable_data ?? [],
				custom: metadata?.custom ?? {},
				steps: metadata?.steps ?? [],
				...metadata?.timing && { timing: metadata.timing },
				...metadata?.submittedFeedback && { submittedFeedback: metadata.submittedFeedback },
				...metadata?.isOptimistic && { isOptimistic: true },
				...metadata?.modality && { modality: metadata.modality }
			}
		};
		case "user": return {
			...common,
			role,
			content: content.map((part) => {
				const type = part.type;
				switch (type) {
					case "text":
					case "image":
					case "audio":
					case "file":
					case "data": return part;
					case "reasoning":
					case "source":
					case "generative-ui":
					case "tool-call": throw new Error(`Unsupported user message part type: ${type}`);
					default: {
						const dataType = type;
						const converted = convertDataPrefixedPart(dataType, part.data, part.id);
						if (converted) return converted;
						throw new Error(`Unsupported user message part type: ${dataType}`);
					}
				}
			}),
			attachments: (attachments ?? []).map((att) => ({
				...att,
				content: att.content.map((part) => {
					return convertDataPrefixedPart(part.type, part.data, "id" in part ? part.id : void 0) ?? part;
				})
			})),
			metadata: {
				custom: metadata?.custom ?? {},
				...metadata?.isOptimistic && { isOptimistic: true },
				...metadata?.modality && { modality: metadata.modality }
			}
		};
		case "system":
			if (content.length !== 1 || content[0].type !== "text") throw new Error("System messages must have exactly one text message part.");
			return {
				...common,
				role,
				content,
				metadata: { custom: metadata?.custom ?? {} }
			};
		default: throw new Error(`Unknown message role: ${role}`);
	}
};
//#endregion
export { fromThreadMessageLike };
