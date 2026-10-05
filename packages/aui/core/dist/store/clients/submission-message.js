import { fromThreadMessageLike } from "../../runtime/utils/thread-message-like.js";
//#region src/store/clients/submission-message.ts
/**
* The thread row for a submission. Its attachments stay on the submission,
* because a message only carries attachments it was delivered with.
*/
const submissionThreadMessage = (submission) => fromThreadMessageLike({
	role: submission.role,
	content: submission.role === "system" || submission.text ? [{
		type: "text",
		text: submission.text
	}] : [],
	attachments: [],
	metadata: { custom: { ...submission.quote ? { quote: submission.quote } : {} } }
}, submission.id, {
	type: "complete",
	reason: "unknown"
});
//#endregion
export { submissionThreadMessage };
