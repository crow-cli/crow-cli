import { ExportedMessageRepository, fromThreadMessageLike } from "@assistant-ui/core";
//#region src/acpMessageProjection.ts
const FALLBACK_STATUS = {
	type: "complete",
	reason: "unknown"
};
const toThreadMessageLike = (message) => message.role === "assistant" ? {
	id: message.id,
	role: "assistant",
	createdAt: new Date(message.createdAt),
	status: message.status,
	content: message.content
} : {
	id: message.id,
	role: "user",
	createdAt: new Date(message.createdAt),
	content: message.content,
	attachments: message.attachments
};
const toThreadMessage = (message) => fromThreadMessageLike(toThreadMessageLike(message), message.id, FALLBACK_STATUS);
function projectAcpThreadRepository(state) {
	return ExportedMessageRepository.fromBranchableArray(state.messageOrder.flatMap((id) => {
		const message = state.messagesById[id];
		return message ? [{
			message: toThreadMessageLike(message),
			parentId: message.parentId
		}] : [];
	}), { headId: state.headId });
}
//#endregion
export { projectAcpThreadRepository, toThreadMessage, toThreadMessageLike };
