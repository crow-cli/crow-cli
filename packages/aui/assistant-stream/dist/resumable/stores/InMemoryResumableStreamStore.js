import { ResumableStreamError, validateStreamId } from "../errors.js";
import "../constants.js";
//#region src/resumable/stores/InMemoryResumableStreamStore.ts
const cursorOf = (seq) => seq.toString(36);
const seqFromCursor = (cursor) => {
	if (cursor === "") return 0;
	const parsed = Number.parseInt(cursor, 36);
	return Number.isNaN(parsed) ? 0 : parsed;
};
function createInMemoryResumableStreamStore(options = {}) {
	let nextToken = 0;
	const streams = /* @__PURE__ */ new Map();
	const defaultTtlMs = options.defaultTtlMs ?? 864e5;
	const now = options.now ?? Date.now;
	const maxChunkBytes = options.maxChunkBytes;
	const maxEntriesPerStream = options.maxEntriesPerStream;
	const maxStreams = options.maxStreams;
	let nextExpiry = Infinity;
	const evictExpired = () => {
		const t = now();
		if (t < nextExpiry) return;
		nextExpiry = Infinity;
		for (const [id, state] of streams) {
			if (state.expiresAt > t) {
				nextExpiry = Math.min(nextExpiry, state.expiresAt);
				continue;
			}
			streams.delete(id);
			state.final ??= {
				kind: "error",
				error: "Stream expired"
			};
			notify(state);
		}
	};
	const notify = (state) => {
		const waiters = state.waiters;
		state.waiters = [];
		for (const wake of waiters) wake();
	};
	const findStartIndex = (state, cursor) => {
		if (cursor === "") return 0;
		const after = seqFromCursor(cursor);
		let lo = 0;
		let hi = state.entries.length;
		while (lo < hi) {
			const mid = lo + hi >>> 1;
			if (seqFromCursor(state.entries[mid].cursor) <= after) lo = mid + 1;
			else hi = mid;
		}
		return lo;
	};
	const waitForUpdate = (state, signal, wakeBy) => new Promise((resolve) => {
		let settled = false;
		let timer;
		const wake = () => {
			if (settled) return;
			settled = true;
			if (timer !== void 0) clearTimeout(timer);
			signal.removeEventListener("abort", wake);
			const idx = state.waiters.indexOf(wake);
			if (idx !== -1) state.waiters.splice(idx, 1);
			resolve();
		};
		if (signal.aborted) {
			wake();
			return;
		}
		state.waiters.push(wake);
		signal.addEventListener("abort", wake, { once: true });
		if (wakeBy !== void 0) {
			if (wakeBy > 0) timer = setTimeout(wake, wakeBy);
			else wake();
		}
	});
	const requireActive = (streamId, lease) => {
		evictExpired();
		const state = streams.get(streamId);
		if (!state) throw new Error(`Stream not found: ${streamId}`);
		if (lease && state.token !== lease.token) throw new ResumableStreamError("missing", `Stream superseded by a new acquisition: ${streamId}`);
		if (state.final) throw new ResumableStreamError("finalized", `Stream already finalized: ${streamId}`);
		return state;
	};
	const gcTimer = options.gcIntervalMs !== void 0 ? setInterval(evictExpired, options.gcIntervalMs) : void 0;
	gcTimer?.unref?.();
	const acquireLease = async (streamId, acquireOptions) => {
		validateStreamId(streamId);
		evictExpired();
		if (streams.get(streamId)) return { role: "consumer" };
		if (maxStreams !== void 0 && streams.size >= maxStreams) throw new Error("maxStreams exceeded");
		const ttlMs = acquireOptions?.ttlMs ?? defaultTtlMs;
		const token = String(++nextToken);
		const expiresAt = now() + ttlMs;
		nextExpiry = Math.min(nextExpiry, expiresAt);
		streams.set(streamId, {
			token,
			entries: [],
			nextSeq: 1,
			expiresAt,
			ttlMs,
			final: void 0,
			waiters: []
		});
		return {
			role: "producer",
			lease: { token }
		};
	};
	return {
		async acquire(streamId, acquireOptions) {
			return (await acquireLease(streamId, acquireOptions)).role;
		},
		acquireLease,
		async append(streamId, chunk, lease) {
			validateStreamId(streamId);
			if (maxChunkBytes !== void 0 && chunk.byteLength > maxChunkBytes) throw new Error(`Chunk exceeds maxChunkBytes: ${chunk.byteLength}`);
			const state = requireActive(streamId, lease);
			if (maxEntriesPerStream !== void 0 && state.entries.length >= maxEntriesPerStream) throw new Error(`Stream exceeded maxEntriesPerStream: ${streamId}`);
			const seq = state.nextSeq;
			state.nextSeq += 1;
			state.entries.push({
				cursor: cursorOf(seq),
				chunk: new Uint8Array(chunk)
			});
			state.expiresAt = now() + state.ttlMs;
			nextExpiry = Math.min(nextExpiry, state.expiresAt);
			notify(state);
		},
		async finalize(streamId, status, error, lease) {
			validateStreamId(streamId);
			evictExpired();
			const state = streams.get(streamId);
			if (!state) throw new Error(`Stream not found: ${streamId}`);
			if (lease && state.token !== lease.token) return false;
			if (state.final) return false;
			state.final = status === "done" ? { kind: "done" } : {
				kind: "error",
				error: error ?? "Stream errored"
			};
			state.expiresAt = now() + state.ttlMs;
			nextExpiry = Math.min(nextExpiry, state.expiresAt);
			notify(state);
			return true;
		},
		async *read(streamId, cursor, signal) {
			validateStreamId(streamId);
			evictExpired();
			const state = streams.get(streamId);
			if (!state) throw new Error(`Stream not found: ${streamId}`);
			let idx = findStartIndex(state, cursor);
			while (true) {
				if (signal.aborted) return;
				while (idx < state.entries.length) {
					if (signal.aborted) return;
					const entry = state.entries[idx];
					yield {
						...entry,
						chunk: new Uint8Array(entry.chunk)
					};
					idx += 1;
				}
				if (signal.aborted) return;
				if (state.final) {
					if (state.final.kind === "error") throw new Error(state.final.error);
					return;
				}
				const wakeBy = state.expiresAt - now();
				await waitForUpdate(state, signal, wakeBy);
				evictExpired();
			}
		},
		async status(streamId) {
			validateStreamId(streamId);
			evictExpired();
			const state = streams.get(streamId);
			if (!state) return "missing";
			if (!state.final) return "streaming";
			return state.final.kind === "error" ? "error" : "done";
		},
		async delete(streamId) {
			validateStreamId(streamId);
			const state = streams.get(streamId);
			if (!state) return;
			streams.delete(streamId);
			state.final ??= { kind: "done" };
			notify(state);
		},
		dispose() {
			if (gcTimer !== void 0) clearInterval(gcTimer);
		}
	};
}
//#endregion
export { createInMemoryResumableStreamStore };
