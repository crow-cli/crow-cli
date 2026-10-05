import { invokeUserCallback } from "../../../utils/invoke-user-callback.js";
import { useLatestRef } from "./useLatestRef.js";
import { useCallback, useEffect, useRef, useState } from "@assistant-ui/tap/react-shim";
import { useReplaySafeEffect } from "@assistant-ui/store/internal";
//#region src/react/runtimes/assistant-transport/runManager.ts
const disposeReason = Symbol("assistant-transport-dispose");
const invokeCallback = (name, callback) => invokeUserCallback("assistant-ui", `Assistant transport ${name}`, callback);
function useRunManager(config) {
	const [isRunning, setIsRunning] = useState(false);
	const stateRef = useRef({
		pending: false,
		disposed: false,
		abortController: null
	});
	const onRunRef = useLatestRef(config.onRun);
	const onFinishRef = useLatestRef(config.onFinish);
	const onCancelRef = useLatestRef(config.onCancel);
	const onErrorRef = useLatestRef(config.onError);
	const startRun = useCallback(() => {
		setIsRunning(true);
		stateRef.current.pending = false;
		const ac = new AbortController();
		stateRef.current.abortController = ac;
		const disposeAborted = () => ac.signal.reason === disposeReason;
		queueMicrotask(async () => {
			try {
				if (!disposeAborted() && !stateRef.current.disposed) {
					await onRunRef.current(ac.signal);
					if (ac.signal.aborted) throw ac.signal.reason;
				}
			} catch (error) {
				if (!disposeAborted() && !stateRef.current.disposed) {
					stateRef.current.pending = false;
					if (ac.signal.aborted) invokeCallback("onCancel", onCancelRef.current);
					else await invokeCallback("onError", () => onErrorRef.current?.(error));
				}
			} finally {
				if (!disposeAborted() && !stateRef.current.disposed) invokeCallback("onFinish", onFinishRef.current);
				if (!stateRef.current.disposed && stateRef.current.pending) startRun();
				else {
					setIsRunning(false);
					if (stateRef.current.abortController === ac) stateRef.current.abortController = null;
				}
			}
		});
	}, [
		onRunRef,
		onFinishRef,
		onErrorRef,
		onCancelRef
	]);
	const schedule = useCallback(() => {
		if (stateRef.current.disposed) return;
		if (stateRef.current.abortController) {
			stateRef.current.pending = true;
			return;
		}
		startRun();
	}, [startRun]);
	useEffect(() => {
		stateRef.current.disposed = false;
		return () => {
			stateRef.current.disposed = true;
		};
	}, []);
	useReplaySafeEffect(() => () => {
		stateRef.current.pending = false;
		stateRef.current.abortController?.abort(disposeReason);
	}, []);
	return {
		isRunning,
		schedule,
		cancel: useCallback(() => {
			stateRef.current.pending = false;
			stateRef.current.abortController?.abort();
		}, [])
	};
}
//#endregion
export { useRunManager };
