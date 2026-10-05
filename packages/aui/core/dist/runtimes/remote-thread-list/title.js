import { AssistantMessageStream } from "assistant-stream";
//#region src/runtimes/remote-thread-list/title.ts
const isTitleSourceMessage = (message) => message.status?.type !== "running";
const applyTitleStream = async (stream, onTitle) => {
	const messageStream = AssistantMessageStream.fromAssistantStream(stream);
	for await (const result of messageStream) {
		const title = result.parts.filter((part) => part.type === "text")[0]?.text;
		if (title?.trim()) await onTitle(title);
	}
};
//#endregion
export { applyTitleStream, isTitleSourceMessage };
