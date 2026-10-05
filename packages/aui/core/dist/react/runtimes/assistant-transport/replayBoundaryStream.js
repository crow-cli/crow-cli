"use client";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useEffect, useRef, useState } from "@assistant-ui/tap/react-shim";
import { useReplaySafeEffect } from "@assistant-ui/store/internal";
//#region src/react/runtimes/assistant-transport/replayBoundaryStream.ts
const REPLAY_CONTENT_LENGTH_HEADER = "Aui-Replay-Content-Length";
const useReplayRenderWait = () => {
	const $ = c(8);
	const [renderTicket, setRenderTicket] = useState(0);
	const mountedRef = useRef(true);
	const nextTicketRef = useRef(0);
	let t0;
	if ($[0] === Symbol.for("react.memo_cache_sentinel")) {
		t0 = [];
		$[0] = t0;
	} else t0 = $[0];
	const waitersRef = useRef(t0);
	let t1;
	if ($[1] === Symbol.for("react.memo_cache_sentinel")) {
		t1 = (committedTicket) => {
			const pendingWaiters = [];
			for (const waiter of waitersRef.current) if (committedTicket === void 0 || waiter.ticket <= committedTicket) waiter.resolve();
			else pendingWaiters.push(waiter);
			waitersRef.current = pendingWaiters;
		};
		$[1] = t1;
	} else t1 = $[1];
	const resolveWaiters = t1;
	let t2;
	let t3;
	if ($[2] !== renderTicket) {
		t2 = () => {
			mountedRef.current = true;
			resolveWaiters(renderTicket);
		};
		t3 = [renderTicket, resolveWaiters];
		$[2] = renderTicket;
		$[3] = t2;
		$[4] = t3;
	} else {
		t2 = $[3];
		t3 = $[4];
	}
	useEffect(t2, t3);
	let t4;
	let t5;
	if ($[5] === Symbol.for("react.memo_cache_sentinel")) {
		t4 = () => () => {
			mountedRef.current = false;
			resolveWaiters();
		};
		t5 = [];
		$[5] = t4;
		$[6] = t5;
	} else {
		t4 = $[5];
		t5 = $[6];
	}
	useReplaySafeEffect(t4, t5);
	let t6;
	if ($[7] === Symbol.for("react.memo_cache_sentinel")) {
		t6 = () => new Promise((resolve) => {
			setTimeout(() => {
				if (!mountedRef.current) {
					resolve();
					return;
				}
				const ticket = nextTicketRef.current + 1;
				nextTicketRef.current = ticket;
				waitersRef.current.push({
					ticket,
					resolve
				});
				setRenderTicket(ticket);
			}, 0);
		});
		$[7] = t6;
	} else t6 = $[7];
	return t6;
};
const parseReplayContentLength = (headers) => {
	const raw = headers.get(REPLAY_CONTENT_LENGTH_HEADER);
	if (raw == null) return 0;
	const boundary = Number(raw);
	return Number.isSafeInteger(boundary) && boundary > 0 ? boundary : 0;
};
const createReplayBoundaryStream = async (response, { setReplaying, waitForRender: waitForReplayRender }) => {
	const body = response.body;
	const replayContentLength = parseReplayContentLength(response.headers);
	if (replayContentLength <= 0) return body;
	setReplaying(true);
	await waitForReplayRender();
	const reader = body.getReader();
	let bytesForwarded = 0;
	let replayFinished = false;
	let replayCleared = false;
	let readerCleanup;
	const clearReplay = () => {
		if (replayCleared) return;
		replayCleared = true;
		setReplaying(false);
	};
	const releaseReader = () => {
		if (readerCleanup) return readerCleanup;
		reader.releaseLock();
		readerCleanup = Promise.resolve();
		return readerCleanup;
	};
	const cancelReader = (reason) => {
		if (readerCleanup) return readerCleanup;
		readerCleanup = (async () => {
			try {
				await reader.cancel(reason);
			} finally {
				reader.releaseLock();
			}
		})();
		return readerCleanup;
	};
	const finishReplay = async () => {
		if (replayFinished) return;
		replayFinished = true;
		await waitForReplayRender();
		clearReplay();
		await waitForReplayRender();
	};
	return new ReadableStream({
		async pull(controller) {
			try {
				const { done, value } = await reader.read();
				if (done) {
					await releaseReader();
					await finishReplay();
					controller.close();
					return;
				}
				if (replayFinished) {
					controller.enqueue(value);
					return;
				}
				const nextBytesForwarded = bytesForwarded + value.byteLength;
				if (nextBytesForwarded < replayContentLength) {
					bytesForwarded = nextBytesForwarded;
					controller.enqueue(value);
					return;
				}
				if (nextBytesForwarded === replayContentLength) {
					controller.enqueue(value);
					await finishReplay();
					return;
				}
				const replayBytesInChunk = replayContentLength - bytesForwarded;
				controller.enqueue(value.subarray(0, replayBytesInChunk));
				await finishReplay();
				controller.enqueue(value.subarray(replayBytesInChunk));
			} catch (error) {
				clearReplay();
				await cancelReader(error).catch(() => {});
				throw error;
			}
		},
		async cancel(reason) {
			const wasFinished = replayFinished;
			replayFinished = true;
			if (!wasFinished) clearReplay();
			await cancelReader(reason);
		}
	});
};
//#endregion
export { REPLAY_CONTENT_LENGTH_HEADER, createReplayBoundaryStream, useReplayRenderWait };
