import { promiseWithResolvers } from "../../../utils/promiseWithResolvers.js";
//#region src/core/utils/stream/merge.ts
const createMergeStream = () => {
	const list = [];
	let sealed = false;
	let cancelled = false;
	let errored = false;
	let controller;
	let rawChunkBatch;
	let pendingRawBatches = 0;
	let currentPull;
	let cleanupPromise;
	const cancelAllReaders = () => {
		rawChunkBatch = void 0;
		cleanupPromise ??= Promise.all(list.splice(0).map(async (item) => {
			try {
				await item.reader.cancel().catch(() => void 0);
				await item.pipeTask;
			} finally {
				item.reader.releaseLock();
			}
		})).then(() => void 0);
		return cleanupPromise;
	};
	const handleError = (e) => {
		if (cancelled || errored) return;
		errored = true;
		console.error(e);
		cancelAllReaders();
		controller.error(e);
		currentPull?.reject(e);
		currentPull = void 0;
	};
	const handlePull = (item) => {
		if (!item.promise) item.promise = item.reader.read().then(({ done, value }) => {
			item.promise = void 0;
			if (cancelled || errored) return;
			if (done) {
				list.splice(list.indexOf(item), 1);
				item.reader.releaseLock();
				if (sealed && list.length === 0 && pendingRawBatches === 0) controller.close();
			} else controller.enqueue(value);
			currentPull?.resolve();
			currentPull = void 0;
		}).catch(handleError);
	};
	const readable = new ReadableStream({
		start(c) {
			controller = c;
		},
		pull() {
			currentPull = promiseWithResolvers();
			list.forEach((item) => {
				handlePull(item);
			});
			return currentPull.promise;
		},
		async cancel() {
			cancelled = true;
			const cleanup = cancelAllReaders();
			currentPull?.resolve();
			currentPull = void 0;
			await cleanup;
		}
	});
	const enqueueRawChunk = (chunk) => {
		if (list.length > 0) rawChunkBatch = void 0;
		if (!rawChunkBatch) {
			const batch = [];
			rawChunkBatch = batch;
			pendingRawBatches++;
			Promise.resolve().then(() => {
				pendingRawBatches--;
				if (rawChunkBatch === batch) rawChunkBatch = void 0;
				if (cancelled || errored) return;
				for (const rawChunk of batch) controller.enqueue(rawChunk);
				if (sealed && list.length === 0 && pendingRawBatches === 0) controller.close();
				currentPull?.resolve();
				currentPull = void 0;
			}).catch(handleError);
		}
		rawChunkBatch.push(chunk);
	};
	const addStream = (stream, pipeTask) => {
		const handledPipeTask = pipeTask?.catch(() => void 0);
		if (cancelled || errored) {
			stream.cancel().catch(() => void 0);
			return;
		}
		if (sealed) {
			stream.cancel().catch(() => void 0);
			throw new Error("Cannot add streams after the run callback has settled.");
		}
		rawChunkBatch = void 0;
		const item = {
			reader: stream.getReader(),
			pipeTask: handledPipeTask
		};
		list.push(item);
		handlePull(item);
	};
	return {
		readable,
		isSealed() {
			return sealed;
		},
		isCancelled() {
			return cancelled;
		},
		isErrored() {
			return errored;
		},
		seal() {
			if (sealed || cancelled || errored) return;
			sealed = true;
			if (list.length === 0 && pendingRawBatches === 0) controller.close();
		},
		addStream,
		enqueue(chunk) {
			if (cancelled || errored) return;
			if (sealed) throw new Error("Cannot add streams after the run callback has settled.");
			enqueueRawChunk(chunk);
		}
	};
};
//#endregion
export { createMergeStream };
