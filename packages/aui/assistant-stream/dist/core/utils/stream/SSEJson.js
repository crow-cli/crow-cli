import { SSEEventDecoderStream } from "./SSEEventDecoderStream.js";
//#region src/core/utils/stream/SSEJson.ts
const SSE_HEADERS = {
	"Content-Type": "text/event-stream",
	"Cache-Control": "no-cache",
	Connection: "keep-alive"
};
const createSSEJsonEncoder = (doneMarker) => (readable) => readable.pipeThrough(new TransformStream({
	transform(chunk, controller) {
		controller.enqueue(`data: ${JSON.stringify(chunk)}\n\n`);
	},
	flush(controller) {
		if (doneMarker !== void 0) controller.enqueue(`data: ${doneMarker}\n\n`);
	}
})).pipeThrough(new TextEncoderStream());
const createSSEJsonDecoder = (options) => (readable) => {
	let receivedDone = false;
	return readable.pipeThrough(new TextDecoderStream()).pipeThrough(new SSEEventDecoderStream()).pipeThrough(new TransformStream({
		transform(event, controller) {
			if (event.event !== "message") {
				if (options.strict !== false) throw new Error(`Unknown SSE event type: ${event.event}`);
				options.onUnknownEvent?.(event.event);
				return;
			}
			if (options.done !== void 0 && event.data === options.done.marker) {
				options.done.onDone?.(controller);
				receivedDone = true;
				controller.terminate();
				return;
			}
			options.parse(event.data, controller);
		},
		flush() {
			if (options.done !== void 0 && !receivedDone) options.done.onMissing?.();
		}
	}));
};
//#endregion
export { SSE_HEADERS, createSSEJsonDecoder, createSSEJsonEncoder };
