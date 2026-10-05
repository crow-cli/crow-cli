//#region src/core/utils/stream/LineDecoderStream.ts
var LineDecoderStream = class extends TransformStream {
	buffer = "";
	skipNextLineFeed = false;
	constructor() {
		super({
			transform: (chunk, controller) => {
				let lineStart = 0;
				for (let i = 0; i < chunk.length; i++) {
					const character = chunk[i];
					if (this.skipNextLineFeed) {
						this.skipNextLineFeed = false;
						if (character === "\n") {
							lineStart = i + 1;
							continue;
						}
					}
					if (character === "\n" || character === "\r") {
						this.buffer += chunk.slice(lineStart, i);
						controller.enqueue(this.buffer);
						this.buffer = "";
						this.skipNextLineFeed = character === "\r";
						lineStart = i + 1;
					}
				}
				this.buffer += chunk.slice(lineStart);
			},
			flush: () => {
				if (this.buffer) throw new Error(`Stream ended with an incomplete line: "${this.buffer}"`);
			}
		});
	}
};
//#endregion
export { LineDecoderStream };
