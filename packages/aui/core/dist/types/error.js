//#region src/types/error.ts
const ERROR_SEVERITIES = [
	"critical",
	"warning",
	"info"
];
const ERROR_DISPLAYS = [
	"inline",
	"toast",
	"silent",
	"dev-only"
];
const isAssistantError = (value) => {
	if (typeof value !== "object" || value === null) return false;
	const candidate = value;
	if (typeof candidate.code !== "string" || typeof candidate.message !== "string") return false;
	if ("severity" in candidate && candidate.severity !== void 0 && (typeof candidate.severity !== "string" || !ERROR_SEVERITIES.includes(candidate.severity))) return false;
	if ("display" in candidate && candidate.display !== void 0 && (typeof candidate.display !== "string" || !ERROR_DISPLAYS.includes(candidate.display))) return false;
	return true;
};
const MESSAGE_NOT_SENT = Symbol.for("assistant-ui.message-not-sent");
/**
* Rejection reason for a send that never reached the backend, so nothing ran
* and nothing is recoverable from the thread. A runtime adapter throws it from
* `onNew` to hand the message back to the thread composer, which restores the
* draft it cleared at dispatch time when nothing has claimed the composer
* since. An edit composer closes at dispatch, so a rejected edit is not
* restored.
*/
var MessageNotSentError = class extends Error {
	[MESSAGE_NOT_SENT] = true;
	constructor(message = "The message was not sent.") {
		super(message);
		this.name = "MessageNotSentError";
	}
};
const isMessageNotSentError = (error) => typeof error === "object" && error !== null && MESSAGE_NOT_SENT in error;
const toAssistantError = (error) => {
	if (isAssistantError(error)) return error;
	if (error instanceof Error) return {
		code: "unknown",
		message: error.message
	};
	if (typeof error === "string") return {
		code: "unknown",
		message: error
	};
	try {
		return {
			code: "unknown",
			message: `[${typeof error}] ${String(error)}`
		};
	} catch {
		return {
			code: "unknown",
			message: `[${typeof error}]`
		};
	}
};
//#endregion
export { MessageNotSentError, isAssistantError, isMessageNotSentError, toAssistantError };
