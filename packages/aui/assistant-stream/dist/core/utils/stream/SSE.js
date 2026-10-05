import { PipeableTransformStream } from "./PipeableTransformStream.js";
import { SSE_HEADERS, createSSEJsonDecoder, createSSEJsonEncoder } from "./SSEJson.js";
import sjson from "secure-json-parse";
//#region src/core/utils/stream/SSE.ts
var SSEEncoder = class SSEEncoder extends PipeableTransformStream {
	static headers = new Headers(SSE_HEADERS);
	headers = SSEEncoder.headers;
	constructor() {
		super(createSSEJsonEncoder());
	}
};
var SSEDecoder = class extends PipeableTransformStream {
	constructor(options = {}) {
		const strict = options.strict ?? true;
		const ignoredEvents = /* @__PURE__ */ new Set();
		super(createSSEJsonDecoder({
			parse(data, controller) {
				let value;
				try {
					value = sjson.parse(data);
				} catch {
					console.warn(`Dropped invalid SSE message: ${data.slice(0, 200)}`);
					return;
				}
				controller.enqueue(value);
			},
			...strict ? { strict: true } : {
				strict: false,
				onUnknownEvent(event) {
					if (!ignoredEvents.has(event)) {
						ignoredEvents.add(event);
						console.error(`Ignored unknown SSE event type: ${event}`);
					}
				}
			}
		}));
	}
};
//#endregion
export { SSEDecoder, SSEEncoder };
