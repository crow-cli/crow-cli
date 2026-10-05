import { GorpStreamAccumulator } from "./GorpStreamAccumulator.js";
import { PipeableTransformStream } from "../utils/stream/PipeableTransformStream.js";
import { SSEDecoder, SSEEncoder } from "../utils/stream/SSE.js";
//#region src/core/gorp/GorpStreamResponse.ts
var GorpStreamEncoder = class extends PipeableTransformStream {
	constructor() {
		let isFirstChunk = true;
		super((readable) => readable.pipeThrough(new TransformStream({ transform(chunk, controller) {
			if (isFirstChunk) controller.enqueue([{
				type: "set",
				path: [],
				value: chunk.snapshot
			}]);
			else controller.enqueue(chunk.operations);
			isFirstChunk = false;
		} })).pipeThrough(new SSEEncoder()));
	}
};
var GorpStreamDecoder = class extends PipeableTransformStream {
	constructor() {
		const accumulator = new GorpStreamAccumulator();
		super((readable) => readable.pipeThrough(new SSEDecoder()).pipeThrough(new TransformStream({ transform(operations, controller) {
			accumulator.append(operations);
			controller.enqueue({
				snapshot: accumulator.state,
				operations
			});
		} })));
	}
};
var GorpStreamResponse = class extends Response {
	constructor(body) {
		super(body.pipeThrough(new GorpStreamEncoder()), { headers: new Headers({
			"Content-Type": "text/event-stream",
			"Cache-Control": "no-cache",
			Connection: "keep-alive",
			"Assistant-Stream-Format": "object-stream/v0"
		}) });
	}
};
const fromGorpStreamResponse = (response) => {
	if (!response.ok) {
		response.body?.cancel().catch(() => void 0);
		throw new Error(`Response failed, status ${response.status}`);
	}
	if (!response.body) throw new Error("Response body is null");
	if (response.headers.get("Content-Type")?.split(";", 1)[0]?.trim().toLowerCase() !== "text/event-stream") {
		response.body?.cancel().catch(() => void 0);
		throw new Error("Response is not an event stream");
	}
	if (response.headers.get("Assistant-Stream-Format") !== "object-stream/v0") {
		response.body?.cancel().catch(() => void 0);
		throw new Error("Unsupported Assistant-Stream-Format header");
	}
	return response.body.pipeThrough(new GorpStreamDecoder());
};
//#endregion
export { GorpStreamDecoder, GorpStreamEncoder, GorpStreamResponse, fromGorpStreamResponse };
