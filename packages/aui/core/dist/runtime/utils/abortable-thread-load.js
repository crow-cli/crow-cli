//#region src/runtime/utils/abortable-thread-load.ts
const createAbortableThreadLoad = () => {
	let current = null;
	return {
		abort(purpose) {
			if (purpose !== void 0 && current?.purpose !== purpose) return;
			current?.controller.abort();
		},
		run({ purpose = "initial", load, onSettled, onInitialError }) {
			if (purpose === "reload" && current?.purpose === "initial") return current.promise ?? Promise.resolve();
			current?.controller.abort();
			const controller = new AbortController();
			const record = {
				controller,
				purpose
			};
			current = record;
			const task = load(controller.signal).catch((error) => {
				if (controller.signal.aborted) return;
				throw error;
			}).finally(() => {
				if (current?.controller === controller) current = null;
				if (controller.signal.aborted) return;
				onSettled();
			});
			record.promise = task;
			if (purpose === "reload") return task;
			return task.catch(onInitialError);
		}
	};
};
//#endregion
export { createAbortableThreadLoad };
