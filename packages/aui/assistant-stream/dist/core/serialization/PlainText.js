import { PipeableTransformStream } from "../utils/stream/PipeableTransformStream.js";
import { AssistantTransformStream } from "../utils/stream/AssistantTransformStream.js";
import { AssistantMetaTransformStream } from "../utils/stream/AssistantMetaTransformStream.js";
//#region src/core/serialization/PlainText.ts
var PlainTextEncoder = class extends PipeableTransformStream {
	headers = new Headers({ "Content-Type": "text/plain; charset=utf-8" });
	constructor() {
		super((readable) => {
			const transform = new TransformStream({ transform(chunk, controller) {
				if (chunk.type === "text-delta" && chunk.meta.type === "text") controller.enqueue(chunk.textDelta);
			} });
			return readable.pipeThrough(new AssistantMetaTransformStream()).pipeThrough(transform).pipeThrough(new TextEncoderStream());
		});
	}
};
var PlainTextDecoder = class extends PipeableTransformStream {
	constructor() {
		super((readable) => {
			const transform = new AssistantTransformStream({ transform(chunk, controller) {
				controller.appendText(chunk);
			} });
			return readable.pipeThrough(new TextDecoderStream()).pipeThrough(transform);
		});
	}
};
//#endregion
export { PlainTextDecoder, PlainTextEncoder };
