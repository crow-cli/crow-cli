import sjson from "secure-json-parse";
//#region src/core/serialization/data-stream/serialization.ts
var DataStreamChunkEncoder = class extends TransformStream {
	constructor() {
		super({ transform: (chunk, controller) => {
			controller.enqueue(`${chunk.type}:${JSON.stringify(chunk.value)}\n`);
		} });
	}
};
var DataStreamChunkDecoder = class extends TransformStream {
	constructor() {
		super({ transform: (chunk, controller) => {
			const index = chunk.indexOf(":");
			if (index === -1) {
				if (chunk.trim().length === 0) return;
				console.warn(`Dropped invalid data-stream chunk: ${chunk.slice(0, 200)}`);
				return;
			}
			let value;
			try {
				value = sjson.parse(chunk.slice(index + 1));
			} catch {
				console.warn(`Dropped invalid data-stream chunk: ${chunk.slice(0, 200)}`);
				return;
			}
			controller.enqueue({
				type: chunk.slice(0, index),
				value
			});
		} });
	}
};
//#endregion
export { DataStreamChunkDecoder, DataStreamChunkEncoder };
