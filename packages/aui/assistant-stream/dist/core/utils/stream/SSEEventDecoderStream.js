import { SSEEventDecoder } from "./SSEEventDecoder.js";
//#region src/core/utils/stream/SSEEventDecoderStream.ts
var SSEEventDecoderStream = class extends TransformStream {
	constructor() {
		const decoder = new SSEEventDecoder({ trailing: "drop" });
		const normalize = (event) => ({
			...event,
			event: event.event || "message"
		});
		super({
			transform(chunk, controller) {
				for (const event of decoder.push(chunk)) controller.enqueue(normalize(event));
			},
			flush(controller) {
				const event = decoder.flush();
				if (event) controller.enqueue(normalize(event));
			}
		});
	}
};
//#endregion
export { SSEEventDecoderStream };
