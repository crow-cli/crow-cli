//#region src/core/utils/stream/createControllerStream.ts
const createControllerStream = (readable, makeController) => new ReadableStream({
	start(controller) {
		return readable.start?.(makeController(controller));
	},
	pull(controller) {
		return readable.pull?.(makeController(controller));
	},
	cancel(reason) {
		return readable.cancel?.(reason);
	}
});
const createControllerStreamPair = (makeController, onCancel) => {
	let controller;
	return [createControllerStream({
		start(value) {
			controller = value;
		},
		cancel(reason) {
			return onCancel?.(controller, reason);
		}
	}, makeController), controller];
};
//#endregion
export { createControllerStream, createControllerStreamPair };
