import { withPromiseOrValue } from "../core/utils/withPromiseOrValue.js";
import { ResumableStreamError } from "./errors.js";
//#region src/resumable/ResumableStreamContext.ts
const invokeObservabilityHook = (name, hook, ...args) => {
	if (!hook) return;
	withPromiseOrValue(() => hook(...args), () => {}, (error) => {
		console.error(`resumable stream ${name} hook failed:`, error);
	});
};
function createResumableStreamContext(options) {
	const { store, waitUntil, onAcquire, onAppend, onFinalize, onError } = options;
	const acquireOptions = options.ttlMs !== void 0 ? { ttlMs: options.ttlMs } : void 0;
	return {
		async run(streamId, makeStream) {
			const acquisition = store.acquireLease ? await store.acquireLease(streamId, acquireOptions) : { role: await store.acquire(streamId, acquireOptions) };
			invokeObservabilityHook("onAcquire", onAcquire, streamId, acquisition.role);
			if (acquisition.role === "producer") startProducerTask(store, streamId, makeStream, {
				waitUntil,
				onAppend,
				onFinalize,
				onError
			}, acquisition.lease);
			return readFromStore(store, streamId);
		},
		async resume(streamId) {
			if (await store.status(streamId) === "missing") return null;
			return readFromStore(store, streamId);
		},
		async requireResume(streamId) {
			if (await store.status(streamId) === "missing") throw new ResumableStreamError("missing", `resumable stream not found: ${streamId}`);
			return readFromStore(store, streamId);
		},
		async status(streamId) {
			return store.status(streamId);
		},
		async delete(streamId) {
			await store.delete(streamId);
		}
	};
}
function startProducerTask(store, streamId, makeStream, hooks, lease) {
	const { waitUntil, onAppend, onFinalize, onError } = hooks;
	const task = (async () => {
		let reader;
		try {
			reader = makeStream().getReader();
			while (true) {
				const { done, value } = await reader.read();
				if (done) break;
				await store.append(streamId, value, lease);
				invokeObservabilityHook("onAppend", onAppend, streamId, value.byteLength);
			}
			if (await store.finalize(streamId, "done", void 0, lease) === false) {
				invokeObservabilityHook("onError", onError, streamId, new ResumableStreamError("missing", `Stream no longer owned by this producer: ${streamId}`));
				return;
			}
			invokeObservabilityHook("onFinalize", onFinalize, streamId, "done");
		} catch (err) {
			invokeObservabilityHook("onError", onError, streamId, err);
			const message = err instanceof Error ? err.message : String(err);
			try {
				await reader?.cancel(err);
			} catch (cancelErr) {
				console.error("resumable stream reader cancel failed:", cancelErr);
			}
			try {
				if (await store.finalize(streamId, "error", message, lease) === false) return;
				invokeObservabilityHook("onFinalize", onFinalize, streamId, "error", message);
			} catch (finalizeErr) {
				console.error("resumable stream finalize failed:", finalizeErr);
			}
		} finally {
			reader?.releaseLock();
		}
	})();
	if (waitUntil) waitUntil(task);
	task.catch((err) => {
		console.error("resumable producer task failed:", err);
	});
}
function readFromStore(store, streamId) {
	const ac = new AbortController();
	let iterator;
	return new ReadableStream({
		start() {
			iterator = store.read(streamId, "", ac.signal)[Symbol.asyncIterator]();
		},
		async pull(controller) {
			try {
				if (!iterator) return;
				const { done, value } = await iterator.next();
				if (done) {
					controller.close();
					return;
				}
				controller.enqueue(value.chunk);
			} catch (err) {
				ac.abort();
				try {
					await iterator?.return?.();
				} catch {}
				controller.error(err);
			}
		},
		async cancel() {
			ac.abort();
			try {
				await iterator?.return?.();
			} catch {}
		}
	});
}
//#endregion
export { createResumableStreamContext };
