import { nullProtoRecord } from "../../utils/record.js";
import { useCallback, useRef } from "@assistant-ui/tap/react-shim";
//#region src/react/interactables-shared/useInteractablePersistenceQueue.ts
const PERSISTENCE_DEBOUNCE_MS = 500;
/**
* `load` is caller code with no settling contract, so an awaited `flush` bounds
* the wait rather than inheriting it. Past this the edit stays queued for the
* next successful snapshot, which is the same shape a failed load already has.
*/
const FLUSH_LOAD_TIMEOUT_MS = 5e3;
const useInteractablePersistenceQueue = ({ adapterRef, adapterGenerationRef, snapshot, updatePersistenceStatus, retainDirtyWithoutAdapter = false }) => {
	const debounceTimerRef = useRef(void 0);
	const syncSeqRef = useRef(0);
	const latestSyncSeqByIdRef = useRef(/* @__PURE__ */ new Map());
	const inFlightPersistenceRef = useRef(0);
	const flushResolversRef = useRef([]);
	const dirtyIdsRef = useRef(/* @__PURE__ */ new Set());
	const outgoingQueueRef = useRef([]);
	const runPersistenceRef = useRef(() => {});
	const takeDirtyBatch = useCallback((adapter) => {
		if (dirtyIdsRef.current.size === 0) return;
		const dirtyIds = new Set(dirtyIdsRef.current);
		dirtyIdsRef.current.clear();
		const seq = ++syncSeqRef.current;
		for (const id of dirtyIds) latestSyncSeqByIdRef.current.set(id, seq);
		return {
			adapter,
			adapterGeneration: adapterGenerationRef.current,
			payload: snapshot(),
			dirtyIds,
			seq
		};
	}, [adapterGenerationRef, snapshot]);
	const enqueuePersistence = useCallback((adapter_0) => {
		const batch = takeDirtyBatch(adapter_0);
		if (!batch) return;
		if (inFlightPersistenceRef.current === 0) runPersistenceRef.current(batch);
		else outgoingQueueRef.current.push(batch);
	}, [takeDirtyBatch]);
	const runPersistence = useCallback(async (batch_0) => {
		const resolved = batch_0 ?? (adapterRef.current ? takeDirtyBatch(adapterRef.current) : void 0);
		if (!resolved) {
			if (inFlightPersistenceRef.current === 0) {
				for (const resolve of flushResolversRef.current) resolve();
				flushResolversRef.current = [];
			}
			return;
		}
		const { adapter: adapter_1, adapterGeneration, payload, dirtyIds: dirtyIds_0, seq: seq_0 } = resolved;
		inFlightPersistenceRef.current += 1;
		updatePersistenceStatus((prev) => {
			const persistence = nullProtoRecord(prev);
			for (const id_0 of dirtyIds_0) persistence[id_0] = {
				isPending: true,
				error: void 0
			};
			return persistence;
		});
		const settleBatch = (status) => {
			const settledIds = [];
			for (const id_1 of dirtyIds_0) {
				if (latestSyncSeqByIdRef.current.get(id_1) !== seq_0 || dirtyIdsRef.current.has(id_1)) continue;
				latestSyncSeqByIdRef.current.delete(id_1);
				settledIds.push(id_1);
			}
			if (settledIds.length === 0) return;
			updatePersistenceStatus((prev_0) => {
				let changed = false;
				const persistence_0 = nullProtoRecord(prev_0);
				for (const id_2 of settledIds) {
					if (prev_0[id_2] === void 0) continue;
					if (status === void 0) delete persistence_0[id_2];
					else persistence_0[id_2] = status;
					changed = true;
				}
				return changed ? persistence_0 : prev_0;
			});
		};
		try {
			await adapter_1.save(payload);
			settleBatch(void 0);
		} catch (e) {
			const isCurrentScope = adapterGenerationRef.current === adapterGeneration;
			if (!isCurrentScope) console.warn("[Interactables] Persistence save failed after the adapter changed.", e);
			settleBatch(isCurrentScope ? {
				isPending: false,
				error: e
			} : void 0);
		} finally {
			inFlightPersistenceRef.current -= 1;
			const next = outgoingQueueRef.current.shift() ?? (adapterRef.current && dirtyIdsRef.current.size > 0 ? takeDirtyBatch(adapterRef.current) : void 0);
			if (next) {
				if (debounceTimerRef.current !== void 0) {
					clearTimeout(debounceTimerRef.current);
					debounceTimerRef.current = void 0;
				}
				runPersistenceRef.current(next);
			} else if (inFlightPersistenceRef.current === 0) {
				for (const resolve of flushResolversRef.current) resolve();
				flushResolversRef.current = [];
			}
		}
	}, [
		adapterGenerationRef,
		adapterRef,
		takeDirtyBatch,
		updatePersistenceStatus
	]);
	runPersistenceRef.current = (nextBatch) => {
		runPersistence(nextBatch);
	};
	const flushIfPending = useCallback(() => {
		if (debounceTimerRef.current !== void 0) {
			clearTimeout(debounceTimerRef.current);
			debounceTimerRef.current = void 0;
		}
		if (adapterRef.current) enqueuePersistence(adapterRef.current);
	}, [adapterRef, enqueuePersistence]);
	const schedulePersistence = useCallback((id_3) => {
		if (!adapterRef.current && !retainDirtyWithoutAdapter) return;
		dirtyIdsRef.current.add(id_3);
		if (!adapterRef.current) return;
		if (debounceTimerRef.current !== void 0) clearTimeout(debounceTimerRef.current);
		debounceTimerRef.current = setTimeout(() => {
			debounceTimerRef.current = void 0;
			if (inFlightPersistenceRef.current === 0 && adapterRef.current) enqueuePersistence(adapterRef.current);
			else debounceTimerRef.current = setTimeout(() => {
				debounceTimerRef.current = void 0;
				if (adapterRef.current) enqueuePersistence(adapterRef.current);
			}, 500);
		}, 500);
	}, [
		adapterRef,
		enqueuePersistence,
		retainDirtyWithoutAdapter
	]);
	return {
		discardPending: useCallback(() => {
			if (debounceTimerRef.current !== void 0) {
				clearTimeout(debounceTimerRef.current);
				debounceTimerRef.current = void 0;
			}
			dirtyIdsRef.current.clear();
			if (inFlightPersistenceRef.current === 0 && outgoingQueueRef.current.length === 0) {
				for (const resolve_0 of flushResolversRef.current) resolve_0();
				flushResolversRef.current = [];
			}
		}, []),
		flushIfPending,
		getDirtyIds: useCallback(() => new Set(dirtyIdsRef.current), []),
		schedulePersistence,
		flush: useCallback(async () => {
			if (debounceTimerRef.current !== void 0) {
				clearTimeout(debounceTimerRef.current);
				debounceTimerRef.current = void 0;
			}
			if (!(inFlightPersistenceRef.current > 0 || outgoingQueueRef.current.length > 0 || adapterRef.current !== void 0 && dirtyIdsRef.current.size > 0)) return;
			const p = new Promise((resolve_1) => {
				flushResolversRef.current.push(resolve_1);
			});
			if (adapterRef.current) enqueuePersistence(adapterRef.current);
			return p;
		}, [adapterRef, enqueuePersistence])
	};
};
//#endregion
export { FLUSH_LOAD_TIMEOUT_MS, PERSISTENCE_DEBOUNCE_MS, useInteractablePersistenceQueue };
