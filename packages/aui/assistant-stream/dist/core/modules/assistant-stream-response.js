import { AssistantStream } from "../AssistantStream.js";
import { createAssistantStream } from "./assistant-stream.js";
import { DataStreamEncoder } from "../serialization/data-stream/DataStream.js";
//#region src/core/modules/assistant-stream-response.ts
/**
* Creates a `Response` whose body is an encoded {@link AssistantStream}.
*
* This is the HTTP-route convenience form of {@link createAssistantStream}; it
* uses {@link DataStreamEncoder} so the response can be consumed by matching
* assistant-ui data stream decoders.
*/
function createAssistantStreamResponse(callback) {
	return AssistantStream.toResponse(createAssistantStream(callback), new DataStreamEncoder());
}
//#endregion
export { createAssistantStreamResponse };
