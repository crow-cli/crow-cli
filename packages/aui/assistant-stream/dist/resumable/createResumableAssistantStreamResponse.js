import { createAssistantStream } from "../core/modules/assistant-stream.js";
import { DataStreamEncoder } from "../core/serialization/data-stream/DataStream.js";
//#region src/resumable/createResumableAssistantStreamResponse.ts
const RESUMABLE_STREAM_ID_HEADER = "x-resumable-stream-id";
async function createResumableAssistantStreamResponse(options) {
	const encoder = (options.encoder ?? (() => new DataStreamEncoder()))();
	const stream = await options.context.run(options.streamId, () => {
		return createAssistantStream(options.callback).pipeThrough(encoder);
	});
	return new Response(stream, { headers: mergeHeaders(encoder.headers, options.headers, options.streamId) });
}
async function createResumeAssistantStreamResponse(options) {
	const stream = await options.context.resume(options.streamId);
	if (!stream) return options.missingResponse?.() ?? defaultMissingResponse();
	const encoder = (options.encoder ?? (() => new DataStreamEncoder()))();
	return new Response(stream, { headers: mergeHeaders(encoder.headers, options.headers, options.streamId) });
}
function defaultMissingResponse() {
	return new Response(JSON.stringify({ error: "stream not found" }), {
		status: 404,
		headers: { "Content-Type": "application/json" }
	});
}
function mergeHeaders(encoderHeaders, extra, streamId) {
	const merged = new Headers(encoderHeaders ?? {});
	if (extra) for (const [key, value] of new Headers(extra)) merged.set(key, value);
	merged.set(RESUMABLE_STREAM_ID_HEADER, streamId);
	return merged;
}
//#endregion
export { RESUMABLE_STREAM_ID_HEADER, createResumableAssistantStreamResponse, createResumeAssistantStreamResponse };
