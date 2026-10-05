import { useCallback, useEffect, useRef, useState } from "@assistant-ui/tap/react-shim";
//#region src/react/runtimes/assistant-transport/commandQueue.ts
const createInitialQueueState = () => ({
	queued: [],
	inTransit: []
});
const useCommandQueue = (opts) => {
	const onQueueRef = useRef(opts.onQueue);
	useEffect(() => {
		onQueueRef.current = opts.onQueue;
	});
	const [, rerender] = useState(0);
	const queueStateRef = useRef(createInitialQueueState());
	const enqueue = (command, options) => {
		queueStateRef.current = {
			queued: [...queueStateRef.current.queued, command],
			inTransit: queueStateRef.current.inTransit
		};
		rerender((prev) => prev + 1);
		if (options?.schedule !== false) onQueueRef.current();
	};
	const flush = () => {
		if (queueStateRef.current.queued.length === 0) return [];
		const queued = queueStateRef.current.queued;
		queueStateRef.current = {
			queued: [],
			inTransit: [...queueStateRef.current.inTransit, ...queued]
		};
		rerender((prev_0) => prev_0 + 1);
		return queued;
	};
	const markDelivered = () => {
		queueStateRef.current = {
			...queueStateRef.current,
			inTransit: []
		};
		rerender((prev_1) => prev_1 + 1);
	};
	return {
		get state() {
			return queueStateRef.current;
		},
		enqueue,
		flush,
		markDelivered,
		reset: useCallback(() => {
			queueStateRef.current = createInitialQueueState();
			rerender((prev_2) => prev_2 + 1);
		}, [])
	};
};
//#endregion
export { createInitialQueueState, useCommandQueue };
