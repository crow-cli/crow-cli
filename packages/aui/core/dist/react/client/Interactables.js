import { nullProtoRecord } from "../../utils/record.js";
import { findModelKnownState, interactableToolName } from "../../model-context/interactable-composer-metadata.js";
import { notifySubscribers } from "../../subscribable/subscribable.js";
import { ModelContext } from "../../store/clients/model-context-client.js";
import { buildInteractableModelContext } from "./interactable-model-context.js";
import { FLUSH_LOAD_TIMEOUT_MS, useInteractablePersistenceQueue } from "../interactables-shared/useInteractablePersistenceQueue.js";
import { attachTransformScopes, useAssistantClientRef, useAssistantScopeEffect } from "@assistant-ui/store/client";
import { toJSONSchema } from "assistant-stream";
import { useCallback, useEffect, useMemo, useRef, useState } from "@assistant-ui/tap/react-shim";
import { resource } from "@assistant-ui/tap";
//#region src/react/client/Interactables.ts
const hasInteractableCreateCall = (messages, id, name) => messages.some((message) => message.role === "assistant" && message.content?.some((part) => {
	if (!part || typeof part !== "object") return false;
	const p = part;
	return p.type === "tool-call" && p.toolCallId === id && p.toolName === name;
}));
const useInteractablesResource = ({ persistence } = {}) => {
	const [state, setState] = useState(() => ({
		definitions: nullProtoRecord(),
		persistence: nullProtoRecord()
	}));
	const clientRef = useAssistantClientRef();
	const clientRefRef = useRef(clientRef);
	clientRefRef.current = clientRef;
	const stateRef = useRef(state);
	const subscribersRef = useRef(/* @__PURE__ */ new Set());
	const schemaCacheRef = useRef(/* @__PURE__ */ new Map());
	const schemaSourceRef = useRef(/* @__PURE__ */ new Map());
	const streamBaselinesRef = useRef(/* @__PURE__ */ new Map());
	const detachedAppStateRef = useRef(/* @__PURE__ */ new Map());
	const detachedThreadStateRef = useRef(/* @__PURE__ */ new Map());
	const registrationCountsRef = useRef(/* @__PURE__ */ new Map());
	const updateToolUIsRef = useRef(/* @__PURE__ */ new Map());
	const loadedStateRef = useRef(/* @__PURE__ */ new Map());
	const touchedIdsRef = useRef(/* @__PURE__ */ new Set());
	const declarativePersistenceRef = useRef(void 0);
	const adapterRef = useRef(void 0);
	const saveAdapterRef = useRef(void 0);
	const adapterLoadRef = useRef(void 0);
	const adapterGenerationRef = useRef(0);
	const lastAttachedAdapterRef = useRef(void 0);
	const adapterPreparationTimerRef = useRef(void 0);
	const setStateAndRef = useCallback((updater) => {
		const next = updater(stateRef.current);
		stateRef.current = next;
		setState(next);
	}, []);
	const exportState = useCallback(() => {
		const result = nullProtoRecord();
		for (const [id, def] of Object.entries(stateRef.current.definitions)) {
			if (def.scope === "thread") continue;
			result[id] = {
				name: def.name,
				state: def.state
			};
		}
		return result;
	}, []);
	const exportPersistenceState = useCallback(() => {
		const threadAccessor = clientRefRef.current.current?.thread;
		const threadMessages = threadAccessor && threadAccessor.source != null ? threadAccessor().getState().messages ?? [] : [];
		const threadCreated = /* @__PURE__ */ new Map();
		for (const message of threadMessages) {
			if (message.role !== "assistant") continue;
			for (const part of message.content ?? []) {
				if (!part || typeof part !== "object") continue;
				const candidate = part;
				if (candidate.type !== "tool-call" || candidate.toolCallId === void 0 || candidate.toolName === void 0) continue;
				let names = threadCreated.get(candidate.toolCallId);
				if (!names) {
					names = /* @__PURE__ */ new Set();
					threadCreated.set(candidate.toolCallId, names);
				}
				names.add(candidate.toolName);
			}
		}
		const isThreadScoped = (id_0, entry) => stateRef.current.definitions[id_0]?.scope === "thread" || threadCreated.get(id_0)?.has(entry.name) === true;
		const result_0 = nullProtoRecord();
		for (const [id_1, entry_0] of loadedStateRef.current) if (!isThreadScoped(id_1, entry_0)) result_0[id_1] = entry_0;
		for (const [id_2, entry_1] of detachedAppStateRef.current) if (!isThreadScoped(id_2, entry_1)) result_0[id_2] = entry_1;
		return Object.assign(result_0, exportState());
	}, [exportState]);
	const updatePersistenceStatus = useCallback((updater_0) => {
		setStateAndRef((prev) => {
			const persistence_0 = updater_0(prev.persistence);
			return persistence_0 === prev.persistence ? prev : {
				...prev,
				persistence: persistence_0
			};
		});
	}, [setStateAndRef]);
	const { discardPending, flushIfPending, getDirtyIds, schedulePersistence, flush: flushPersistence } = useInteractablePersistenceQueue({
		adapterRef: saveAdapterRef,
		adapterGenerationRef,
		snapshot: exportPersistenceState,
		updatePersistenceStatus,
		retainDirtyWithoutAdapter: true
	});
	const restorePersistedState = useCallback((saved, options) => {
		const shouldStash = options.shouldStash ?? (() => true);
		const shouldApply = options.shouldApply ?? (() => true);
		for (const [id_3, entry_2] of Object.entries(saved)) if (shouldStash(id_3)) options.stash.set(id_3, entry_2);
		setStateAndRef((prev_0) => {
			let changed = false;
			const definitions = nullProtoRecord(prev_0.definitions);
			for (const [id_4, entry_3] of Object.entries(saved)) {
				const def_0 = definitions[id_4];
				if (!def_0 || !shouldApply(id_4, def_0)) continue;
				definitions[id_4] = {
					...def_0,
					state: entry_3.state
				};
				changed = true;
			}
			if (!changed) return prev_0;
			return {
				...prev_0,
				definitions
			};
		});
	}, [setStateAndRef]);
	const importState = useCallback((saved_0) => {
		restorePersistedState(saved_0, { stash: detachedAppStateRef.current });
	}, [restorePersistedState]);
	const applyLoadedState = useCallback((saved_1) => {
		restorePersistedState(saved_1, {
			stash: loadedStateRef.current,
			shouldStash: (id_5) => !touchedIdsRef.current.has(id_5),
			shouldApply: (id_6, def_1) => !touchedIdsRef.current.has(id_6) && def_1.scope !== "thread"
		});
	}, [restorePersistedState]);
	const loadFromAdapter = useCallback(async (adapter) => {
		if (!adapter.load) return { status: "loaded" };
		try {
			const saved_2 = await adapter.load();
			if (adapterRef.current !== adapter) return { status: "stale" };
			if (saved_2) applyLoadedState(saved_2);
			return { status: "loaded" };
		} catch (e) {
			console.warn("[Interactables] Persistence load failed.", e);
			return {
				status: "error",
				error: e
			};
		}
	}, [applyLoadedState]);
	const updateDirtyLoadStatus = useCallback((status) => {
		const dirtyIds = getDirtyIds();
		if (dirtyIds.size === 0) return;
		updatePersistenceStatus((prev_1) => {
			let changed_0 = false;
			const persistence_1 = nullProtoRecord(prev_1);
			for (const id_7 of dirtyIds) {
				if (stateRef.current.definitions[id_7] === void 0) continue;
				if (prev_1[id_7]?.isPending === status.isPending && prev_1[id_7]?.error === status.error) continue;
				persistence_1[id_7] = status;
				changed_0 = true;
			}
			return changed_0 ? persistence_1 : prev_1;
		});
	}, [getDirtyIds, updatePersistenceStatus]);
	const prepareAdapter = useCallback((adapter_0) => {
		if (saveAdapterRef.current === adapter_0) return Promise.resolve(true);
		updateDirtyLoadStatus({
			isPending: true,
			error: void 0
		});
		const currentLoad = adapterLoadRef.current;
		if (currentLoad?.adapter === adapter_0) return currentLoad.promise;
		let promise;
		promise = loadFromAdapter(adapter_0).then((result_1) => {
			if (adapterLoadRef.current?.promise === promise) adapterLoadRef.current = void 0;
			if (adapterRef.current !== adapter_0) return false;
			if (result_1.status === "error") {
				updateDirtyLoadStatus({
					isPending: false,
					error: result_1.error
				});
				return false;
			}
			if (result_1.status !== "loaded") return false;
			if (adapterPreparationTimerRef.current !== void 0) {
				clearTimeout(adapterPreparationTimerRef.current);
				adapterPreparationTimerRef.current = void 0;
			}
			saveAdapterRef.current = adapter_0;
			flushIfPending();
			return true;
		});
		adapterLoadRef.current = {
			adapter: adapter_0,
			promise
		};
		return promise;
	}, [
		flushIfPending,
		loadFromAdapter,
		updateDirtyLoadStatus
	]);
	const scheduleAdapterPreparation = useCallback((adapter_1) => {
		if (adapterPreparationTimerRef.current !== void 0) clearTimeout(adapterPreparationTimerRef.current);
		adapterPreparationTimerRef.current = setTimeout(() => {
			adapterPreparationTimerRef.current = void 0;
			if (adapterRef.current === adapter_1 && saveAdapterRef.current !== adapter_1) prepareAdapter(adapter_1);
		}, 500);
	}, [prepareAdapter]);
	const resetPersistenceScope = useCallback(() => {
		loadedStateRef.current.clear();
		touchedIdsRef.current.clear();
		detachedAppStateRef.current.clear();
		for (const [toolCallId, baseline] of streamBaselinesRef.current) if (stateRef.current.definitions[baseline.targetId]?.scope !== "thread") streamBaselinesRef.current.delete(toolCallId);
		setStateAndRef((prev_2) => {
			let changed_1 = false;
			const definitions_0 = nullProtoRecord(prev_2.definitions);
			for (const [id_8, def_2] of Object.entries(definitions_0)) {
				if (def_2.scope === "thread") continue;
				definitions_0[id_8] = {
					...def_2,
					state: def_2.initialState
				};
				changed_1 = true;
			}
			const persistence_2 = nullProtoRecord(prev_2.persistence);
			for (const id_9 of Object.keys(prev_2.persistence)) {
				delete persistence_2[id_9];
				changed_1 = true;
			}
			return changed_1 ? {
				...prev_2,
				definitions: definitions_0,
				persistence: persistence_2
			} : prev_2;
		});
	}, [setStateAndRef]);
	const setPersistenceAdapter = useCallback((adapter_2) => {
		if (adapterRef.current !== adapter_2) {
			if (adapterPreparationTimerRef.current !== void 0) {
				clearTimeout(adapterPreparationTimerRef.current);
				adapterPreparationTimerRef.current = void 0;
			}
			flushIfPending();
			saveAdapterRef.current = void 0;
		}
		adapterRef.current = adapter_2;
		if (!adapter_2) {
			const dirtyIds_0 = getDirtyIds();
			if (dirtyIds_0.size > 0) updatePersistenceStatus((prev_3) => {
				let changed_2 = false;
				const persistence_3 = nullProtoRecord(prev_3);
				for (const id_10 of dirtyIds_0) {
					if (prev_3[id_10] === void 0) continue;
					delete persistence_3[id_10];
					changed_2 = true;
				}
				return changed_2 ? persistence_3 : prev_3;
			});
			adapterLoadRef.current = void 0;
			return;
		}
		const lastAttached = lastAttachedAdapterRef.current;
		lastAttachedAdapterRef.current = adapter_2;
		if (lastAttached !== void 0 && lastAttached !== adapter_2) {
			discardPending();
			adapterGenerationRef.current += 1;
			if (process.env.NODE_ENV !== "production") console.warn("[Interactables] The persistence adapter identity changed, so app-scoped state was reset for the new scope. Memoize the adapter unless this is an account or workspace switch.");
			resetPersistenceScope();
		}
		prepareAdapter(adapter_2);
	}, [
		discardPending,
		flushIfPending,
		getDirtyIds,
		prepareAdapter,
		resetPersistenceScope,
		updatePersistenceStatus
	]);
	useEffect(() => () => {
		if (adapterPreparationTimerRef.current !== void 0) clearTimeout(adapterPreparationTimerRef.current);
	}, []);
	const flush = useCallback(async () => {
		const adapter_3 = adapterRef.current;
		if (adapter_3 && saveAdapterRef.current !== adapter_3) {
			let timer;
			try {
				await Promise.race([prepareAdapter(adapter_3), new Promise((resolve) => {
					timer = setTimeout(() => resolve(false), FLUSH_LOAD_TIMEOUT_MS);
				})]);
			} finally {
				if (timer !== void 0) clearTimeout(timer);
			}
		}
		await flushPersistence();
	}, [flushPersistence, prepareAdapter]);
	const getCurrentThreadId = useCallback(() => {
		const client = clientRef.current;
		if (!client) return void 0;
		const threadListItem = client.threadListItem;
		if (threadListItem.source != null) return threadListItem().getState().id;
		const threads = client.threads;
		if (threads.source != null) return threads().getState().mainThreadId;
	}, [clientRef]);
	useEffect(() => {
		if (!persistence && !declarativePersistenceRef.current) return;
		declarativePersistenceRef.current = persistence;
		setPersistenceAdapter(persistence);
	}, [persistence, setPersistenceAdapter]);
	useEffect(() => {
		return () => {
			if (!declarativePersistenceRef.current) return;
			declarativePersistenceRef.current = void 0;
			setPersistenceAdapter(void 0);
		};
	}, [setPersistenceAdapter]);
	const setDefState = useCallback((id_11, updater_1) => {
		if (!stateRef.current.definitions[id_11]) return;
		touchedIdsRef.current.add(id_11);
		setStateAndRef((prev_4) => {
			const existing = prev_4.definitions[id_11];
			return {
				...prev_4,
				definitions: nullProtoRecord(prev_4.definitions, { [id_11]: {
					...existing,
					state: updater_1(existing.state)
				} })
			};
		});
		if (stateRef.current.definitions[id_11]?.scope !== "thread") {
			schedulePersistence(id_11);
			const adapter_4 = adapterRef.current;
			if (adapter_4 && saveAdapterRef.current !== adapter_4) {
				updateDirtyLoadStatus({
					isPending: true,
					error: void 0
				});
				scheduleAdapterPreparation(adapter_4);
			}
		}
	}, [
		scheduleAdapterPreparation,
		schedulePersistence,
		setStateAndRef,
		updateDirtyLoadStatus
	]);
	const provider = useMemo(() => ({
		getModelContext: () => {
			const defs = stateRef.current.definitions;
			return buildInteractableModelContext(defs, schemaCacheRef.current, setDefState, () => stateRef.current.definitions, streamBaselinesRef.current) ?? {};
		},
		subscribe: (callback) => {
			subscribersRef.current.add(callback);
			return () => {
				subscribersRef.current.delete(callback);
			};
		}
	}), [setDefState]);
	useEffect(() => {
		notifySubscribers(subscribersRef.current);
	}, [state]);
	useAssistantScopeEffect("modelContext", () => clientRef.current.modelContext().register(provider), [provider]);
	const installUpdateToolUI = useCallback((name, entry_4) => {
		const toolsAccessor = clientRef.current?.tools;
		if (!toolsAccessor || toolsAccessor.source == null) return false;
		entry_4.unsubscribe = toolsAccessor().setToolUI(interactableToolName(name), entry_4.render, { standalone: true });
		return true;
	}, [clientRef]);
	useAssistantScopeEffect("tools", () => {
		for (const [name_0, entry_5] of updateToolUIsRef.current) {
			entry_5.unsubscribe?.();
			entry_5.unsubscribe = void 0;
			installUpdateToolUI(name_0, entry_5);
		}
		return () => {
			for (const entry_6 of updateToolUIsRef.current.values()) {
				entry_6.unsubscribe?.();
				entry_6.unsubscribe = void 0;
			}
		};
	}, [installUpdateToolUI]);
	return {
		getState: () => stateRef.current,
		register: useCallback((def_3) => {
			const threadAccessor_0 = clientRef.current?.thread;
			const threadMessages_0 = threadAccessor_0 && threadAccessor_0.source != null ? threadAccessor_0().getState().messages ?? [] : [];
			const scope = def_3.scope ?? (hasInteractableCreateCall(threadMessages_0, def_3.id, def_3.name) ? "thread" : "app");
			if (process.env.NODE_ENV !== "production" && stateRef.current.definitions[def_3.id] && scope !== "thread") console.warn(`[Interactables] "${def_3.name}" (${def_3.id}) is already registered. Register an app-scoped interactable once (unstable_useInteractable) and read it from other components with unstable_useInteractableState.`);
			registrationCountsRef.current.set(def_3.id, (registrationCountsRef.current.get(def_3.id) ?? 0) + 1);
			let releaseUpdateToolUI;
			if (def_3.updateRender) {
				const existing_0 = updateToolUIsRef.current.get(def_3.name);
				const entry_7 = existing_0 ?? {
					count: 0,
					render: def_3.updateRender,
					unsubscribe: void 0
				};
				entry_7.count++;
				if (!existing_0) updateToolUIsRef.current.set(def_3.name, entry_7);
				if (!entry_7.unsubscribe && !installUpdateToolUI(def_3.name, entry_7) && process.env.NODE_ENV !== "production") console.warn(`[Interactables] "${def_3.name}" supplied an updateRender, but no tools scope is available yet; it will be installed once one appears.`);
				releaseUpdateToolUI = () => {
					const entry_8 = updateToolUIsRef.current.get(def_3.name);
					if (!entry_8) return;
					if (--entry_8.count === 0) {
						updateToolUIsRef.current.delete(def_3.name);
						entry_8.unsubscribe?.();
						entry_8.unsubscribe = void 0;
					}
				};
			}
			if (schemaSourceRef.current.get(def_3.id) !== def_3.stateSchema) {
				schemaSourceRef.current.set(def_3.id, def_3.stateSchema);
				schemaCacheRef.current.delete(def_3.id);
				try {
					const jsonSchema = toJSONSchema(def_3.stateSchema);
					schemaCacheRef.current.set(def_3.id, jsonSchema);
				} catch (e_0) {
					console.warn(`[Interactables] Failed to convert the state schema of "${def_3.name}" to JSON Schema. The update tool will accept arbitrary fields without validation.`, e_0);
				}
			}
			const threadId = scope === "thread" ? getCurrentThreadId() : void 0;
			const detachedState = scope === "thread" ? threadId ? detachedThreadStateRef.current.get(threadId)?.get(def_3.id) : void 0 : detachedAppStateRef.current.get(def_3.id)?.state;
			if (scope === "thread") {
				loadedStateRef.current.delete(def_3.id);
				if (threadId) detachedThreadStateRef.current.get(threadId)?.delete(def_3.id);
			} else detachedAppStateRef.current.delete(def_3.id);
			const loadedState = scope === "thread" ? void 0 : loadedStateRef.current.get(def_3.id)?.state;
			const known = scope === "thread" ? findModelKnownState(threadMessages_0, def_3.id, def_3.name) : void 0;
			setStateAndRef((prev_5) => ({
				...prev_5,
				definitions: nullProtoRecord(prev_5.definitions, { [def_3.id]: {
					id: def_3.id,
					name: def_3.name,
					description: def_3.description,
					stateSchema: def_3.stateSchema,
					initialState: def_3.initialState,
					scope,
					state: prev_5.definitions[def_3.id]?.state ?? detachedState ?? known?.state ?? loadedState ?? def_3.initialState
				} })
			}));
			return () => {
				releaseUpdateToolUI?.();
				const remaining = (registrationCountsRef.current.get(def_3.id) ?? 1) - 1;
				if (remaining > 0) {
					registrationCountsRef.current.set(def_3.id, remaining);
					return;
				}
				registrationCountsRef.current.delete(def_3.id);
				flushIfPending();
				setStateAndRef((prev_6) => {
					const existing_1 = prev_6.definitions[def_3.id];
					if (existing_1) {
						if (existing_1.scope === "thread") {
							const threadId_0 = getCurrentThreadId();
							if (threadId_0) {
								let stateById = detachedThreadStateRef.current.get(threadId_0);
								if (!stateById) {
									stateById = /* @__PURE__ */ new Map();
									detachedThreadStateRef.current.set(threadId_0, stateById);
								}
								stateById.set(def_3.id, existing_1.state);
							}
						} else detachedAppStateRef.current.set(def_3.id, {
							name: existing_1.name,
							state: existing_1.state
						});
					}
					schemaSourceRef.current.delete(def_3.id);
					schemaCacheRef.current.delete(def_3.id);
					const definitions_1 = nullProtoRecord(prev_6.definitions);
					const persistence_4 = nullProtoRecord(prev_6.persistence);
					delete definitions_1[def_3.id];
					delete persistence_4[def_3.id];
					return {
						...prev_6,
						definitions: definitions_1,
						persistence: persistence_4
					};
				});
			};
		}, [
			flushIfPending,
			clientRef,
			getCurrentThreadId,
			installUpdateToolUI,
			setStateAndRef
		]),
		setState: setDefState,
		exportState,
		importState,
		setPersistenceAdapter,
		flush
	};
};
/**
* Registers the unstable interactables store scope.
*
* @deprecated Unstable / Experimental (not actually removed).
*/
const unstable_Interactables = resource(useInteractablesResource);
attachTransformScopes(useInteractablesResource, (scopes, parent) => {
	if (!scopes.modelContext && parent.modelContext.source === null) scopes.modelContext = ModelContext();
});
//#endregion
export { unstable_Interactables };
