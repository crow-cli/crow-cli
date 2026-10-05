import { createAssistantStreamController } from "../../modules/assistant-stream.js";
//#region src/core/utils/stream/AssistantTransformStream.ts
var AssistantTransformStream = class extends TransformStream {
	constructor(transformer, writableStrategy, readableStrategy) {
		const [stream, runController] = createAssistantStreamController({ strict: transformer.strict });
		const abortController = new AbortController();
		let runPipeTask;
		super({
			start(controller) {
				runPipeTask = stream.pipeTo(new WritableStream({
					write(chunk) {
						controller.enqueue(chunk);
					},
					abort(reason) {
						controller.error(reason);
					},
					close() {
						controller.terminate();
					}
				}), { signal: abortController.signal }).catch((error) => {
					controller.error(error);
				});
				try {
					return transformer.start?.(runController);
				} catch (error) {
					abortController.abort(error);
					throw error;
				}
			},
			transform(chunk) {
				return transformer.transform?.(chunk, runController);
			},
			async flush() {
				await transformer.flush?.(runController);
				runController.close();
				await runPipeTask;
			}
		}, writableStrategy, readableStrategy);
		const reader = super.readable.getReader();
		let cancelled = false;
		Object.defineProperty(this, "readable", {
			value: new ReadableStream({
				start(controller) {
					reader.closed.catch((error) => {
						abortController.abort(error);
						controller.error(error);
						reader.releaseLock();
					});
				},
				async pull(controller) {
					const result = await reader.read();
					if (cancelled) return;
					if (result.done) {
						controller.close();
						reader.releaseLock();
					} else controller.enqueue(result.value);
				},
				async cancel(reason) {
					cancelled = true;
					const cancellation = reader.cancel(reason);
					abortController.abort(reason);
					try {
						await cancellation;
					} finally {
						await runPipeTask;
						reader.releaseLock();
					}
				}
			}, { highWaterMark: 0 }),
			writable: false
		});
	}
};
//#endregion
export { AssistantTransformStream };
