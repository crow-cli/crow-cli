//#region src/utils/abortable-iterable.ts
const done = () => ({
	done: true,
	value: void 0
});
const openAbortableIterable = async (source, signal) => {
	const opened = Promise.resolve(source);
	let release = () => {};
	const aborted = new Promise((resolve) => {
		const onAbort = () => resolve(void 0);
		if (signal.aborted) return onAbort();
		signal.addEventListener("abort", onAbort, { once: true });
		release = () => signal.removeEventListener("abort", onAbort);
	});
	try {
		const iterable = await Promise.race([opened, aborted]);
		if (!iterable) opened.then((late) => late[Symbol.asyncIterator]().return?.(void 0)).catch(() => {});
		return iterable;
	} finally {
		release();
	}
};
/**
* Presents a stream as exhausted once the signal aborts, so a consumer stops
* waiting on it.
*
* A caller's stream is free to ignore the abort signal it is handed. One that
* also stops yielding, because it is awaiting its own work, leaves `for await`
* parked on `next()` with nothing left to wake it: the run never settles and
* whatever is serialized behind it never starts. Reporting the stream as
* exhausted ends the loop at cancellation instead.
*
* The source is finalized on the way out, but never awaited, since a stream
* that is already parked would not settle that either.
*/
const abortableIterable = (source, signal) => ({ [Symbol.asyncIterator]: () => {
	const iterator = source[Symbol.asyncIterator]();
	let finished = false;
	const finalize = () => {
		if (finished) return;
		finished = true;
		try {
			iterator.return?.(void 0)?.catch(() => {});
		} catch {}
	};
	return {
		[Symbol.asyncIterator]() {
			return this;
		},
		next: () => {
			if (finished || signal.aborted) {
				finalize();
				return Promise.resolve(done());
			}
			return new Promise((resolve, reject) => {
				const onAbort = () => {
					finalize();
					resolve(done());
				};
				signal.addEventListener("abort", onAbort, { once: true });
				const release = () => signal.removeEventListener("abort", onAbort);
				const onError = (error) => {
					release();
					finalize();
					reject(error);
				};
				try {
					iterator.next().then((result) => {
						release();
						if (finished) return resolve(done());
						if (result.done) finished = true;
						resolve(result);
					}, onError);
				} catch (error) {
					onError(error);
				}
			});
		},
		return: async () => {
			finalize();
			return done();
		}
	};
} });
//#endregion
export { abortableIterable, openAbortableIterable };
