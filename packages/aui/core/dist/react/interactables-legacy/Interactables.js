import { nullProtoRecord } from "../../utils/record.js";
import { notifySubscribers } from "../../subscribable/subscribable.js";
import { ModelContext } from "../../store/clients/model-context-client.js";
import { useInteractablePersistenceQueue } from "../interactables-shared/useInteractablePersistenceQueue.js";
import { buildInteractableModelContext } from "./interactable-model-context.js";
import { useAssistantScopeEffect } from "@assistant-ui/store/client";
import { toJSONSchema } from "assistant-stream";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useEffect, useRef, useState } from "@assistant-ui/tap/react-shim";
import { attachTransformScopes as attachTransformScopes$1, useAssistantClientRef as useAssistantClientRef$1 } from "@assistant-ui/store";
import { resource } from "@assistant-ui/tap";
//#region src/react/interactables-legacy/Interactables.ts
const useInteractables = () => {
	const $ = c(36);
	const [state, setState] = useState(_temp);
	const clientRef = useAssistantClientRef$1();
	const stateRef = useRef(state);
	let t0;
	if ($[0] === Symbol.for("react.memo_cache_sentinel")) {
		t0 = (updater) => {
			const next = updater(stateRef.current);
			stateRef.current = next;
			setState(next);
		};
		$[0] = t0;
	} else t0 = $[0];
	const setStateAndRef = t0;
	let t1;
	if ($[1] === Symbol.for("react.memo_cache_sentinel")) {
		t1 = /* @__PURE__ */ new Set();
		$[1] = t1;
	} else t1 = $[1];
	const subscribersRef = useRef(t1);
	let t2;
	if ($[2] === Symbol.for("react.memo_cache_sentinel")) {
		t2 = /* @__PURE__ */ new Map();
		$[2] = t2;
	} else t2 = $[2];
	const schemaCacheRef = useRef(t2);
	let t3;
	if ($[3] === Symbol.for("react.memo_cache_sentinel")) {
		t3 = /* @__PURE__ */ new Map();
		$[3] = t3;
	} else t3 = $[3];
	const detachedStateRef = useRef(t3);
	const adapterRef = useRef(void 0);
	const adapterGenerationRef = useRef(0);
	const lastAttachedAdapterRef = useRef(void 0);
	let t4;
	if ($[4] === Symbol.for("react.memo_cache_sentinel")) {
		t4 = () => {
			const result = nullProtoRecord();
			for (const [id, def] of Object.entries(stateRef.current.definitions)) result[id] = {
				name: def.name,
				state: def.state
			};
			return result;
		};
		$[4] = t4;
	} else t4 = $[4];
	const exportState = t4;
	let t5;
	if ($[5] === Symbol.for("react.memo_cache_sentinel")) {
		t5 = (updater_0) => {
			setStateAndRef((prev) => {
				const persistence = updater_0(prev.persistence);
				return persistence === prev.persistence ? prev : {
					...prev,
					persistence
				};
			});
		};
		$[5] = t5;
	} else t5 = $[5];
	const updatePersistenceStatus = t5;
	let t6;
	if ($[6] === Symbol.for("react.memo_cache_sentinel")) {
		t6 = {
			adapterRef,
			adapterGenerationRef,
			snapshot: exportState,
			updatePersistenceStatus
		};
		$[6] = t6;
	} else t6 = $[6];
	const { flushIfPending, schedulePersistence, flush } = useInteractablePersistenceQueue(t6);
	let t7;
	if ($[7] === Symbol.for("react.memo_cache_sentinel")) {
		t7 = (saved) => {
			for (const [id_0, entry] of Object.entries(saved)) detachedStateRef.current.set(id_0, entry.state);
			setStateAndRef((prev_0) => {
				let changed = false;
				const definitions = nullProtoRecord(prev_0.definitions);
				for (const [id_1, entry_0] of Object.entries(saved)) if (definitions[id_1]) {
					definitions[id_1] = {
						...definitions[id_1],
						state: entry_0.state
					};
					changed = true;
				}
				return changed ? {
					...prev_0,
					definitions
				} : prev_0;
			});
		};
		$[7] = t7;
	} else t7 = $[7];
	const importState = t7;
	let t8;
	if ($[8] !== flushIfPending) {
		t8 = (adapter) => {
			if (adapterRef.current !== adapter) flushIfPending();
			adapterRef.current = adapter;
			if (!adapter) return;
			const lastAttached = lastAttachedAdapterRef.current;
			lastAttachedAdapterRef.current = adapter;
			if (lastAttached !== void 0 && lastAttached !== adapter) adapterGenerationRef.current = adapterGenerationRef.current + 1;
		};
		$[8] = flushIfPending;
		$[9] = t8;
	} else t8 = $[9];
	const setPersistenceAdapter = t8;
	let t9;
	if ($[10] !== schedulePersistence) {
		t9 = (id_2, updater_1) => {
			setStateAndRef((prev_1) => {
				const existing = prev_1.definitions[id_2];
				if (!existing) return prev_1;
				return {
					...prev_1,
					definitions: nullProtoRecord(prev_1.definitions, { [id_2]: {
						...existing,
						state: updater_1(existing.state)
					} })
				};
			});
			if (stateRef.current.definitions[id_2]) schedulePersistence(id_2);
		};
		$[10] = schedulePersistence;
		$[11] = t9;
	} else t9 = $[11];
	const setDefState = t9;
	let t10;
	if ($[12] === Symbol.for("react.memo_cache_sentinel")) {
		t10 = (id_3, selected) => {
			setStateAndRef((prev_2) => {
				const existing_0 = prev_2.definitions[id_3];
				if (!existing_0) return prev_2;
				return {
					...prev_2,
					definitions: nullProtoRecord(prev_2.definitions, { [id_3]: {
						...existing_0,
						selected
					} })
				};
			});
		};
		$[12] = t10;
	} else t10 = $[12];
	const setDefSelected = t10;
	let t11;
	if ($[13] !== setDefState) {
		t11 = () => {
			const defs = stateRef.current.definitions;
			return buildInteractableModelContext(defs, schemaCacheRef.current, setDefState) ?? {};
		};
		$[13] = setDefState;
		$[14] = t11;
	} else t11 = $[14];
	let t12;
	if ($[15] === Symbol.for("react.memo_cache_sentinel")) {
		t12 = (callback) => {
			subscribersRef.current.add(callback);
			return () => {
				subscribersRef.current.delete(callback);
			};
		};
		$[15] = t12;
	} else t12 = $[15];
	let t13;
	if ($[16] !== t11) {
		t13 = {
			getModelContext: t11,
			subscribe: t12
		};
		$[16] = t11;
		$[17] = t13;
	} else t13 = $[17];
	const provider = t13;
	let t14;
	if ($[18] === Symbol.for("react.memo_cache_sentinel")) {
		t14 = () => {
			notifySubscribers(subscribersRef.current);
		};
		$[18] = t14;
	} else t14 = $[18];
	let t15;
	if ($[19] !== state) {
		t15 = [state];
		$[19] = state;
		$[20] = t15;
	} else t15 = $[20];
	useEffect(t14, t15);
	let t16;
	if ($[21] !== clientRef || $[22] !== provider) {
		t16 = () => clientRef.current.modelContext().register(provider);
		$[21] = clientRef;
		$[22] = provider;
		$[23] = t16;
	} else t16 = $[23];
	let t17;
	if ($[24] !== provider) {
		t17 = [provider];
		$[24] = provider;
		$[25] = t17;
	} else t17 = $[25];
	useAssistantScopeEffect("modelContext", t16, t17);
	let t18;
	if ($[26] !== flushIfPending) {
		t18 = (def_0) => {
			schemaCacheRef.current.delete(def_0.id);
			try {
				schemaCacheRef.current.set(def_0.id, toJSONSchema(def_0.stateSchema));
			} catch (t19) {
				const e = t19;
				console.warn(`[Interactables] Failed to convert the state schema of "${def_0.name}" to JSON Schema. The update tool will require all fields.`, e);
			}
			const detached = detachedStateRef.current.get(def_0.id);
			detachedStateRef.current.delete(def_0.id);
			setStateAndRef((prev_3) => ({
				...prev_3,
				definitions: nullProtoRecord(prev_3.definitions, { [def_0.id]: {
					id: def_0.id,
					name: def_0.name,
					description: def_0.description,
					stateSchema: def_0.stateSchema,
					state: prev_3.definitions[def_0.id]?.state ?? detached ?? def_0.initialState,
					selected: def_0.selected
				} })
			}));
			return () => {
				flushIfPending();
				setStateAndRef((prev_4) => {
					const existing_1 = prev_4.definitions[def_0.id];
					if (existing_1) detachedStateRef.current.set(def_0.id, existing_1.state);
					schemaCacheRef.current.delete(def_0.id);
					const definitions_0 = nullProtoRecord(prev_4.definitions);
					const persistence_0 = nullProtoRecord(prev_4.persistence);
					delete definitions_0[def_0.id];
					delete persistence_0[def_0.id];
					return {
						...prev_4,
						definitions: definitions_0,
						persistence: persistence_0
					};
				});
			};
		};
		$[26] = flushIfPending;
		$[27] = t18;
	} else t18 = $[27];
	const register = t18;
	let t19;
	if ($[28] !== state) {
		t19 = () => state;
		$[28] = state;
		$[29] = t19;
	} else t19 = $[29];
	let t20;
	if ($[30] !== flush || $[31] !== register || $[32] !== setDefState || $[33] !== setPersistenceAdapter || $[34] !== t19) {
		t20 = {
			getState: t19,
			register,
			setState: setDefState,
			setSelected: setDefSelected,
			exportState,
			importState,
			setPersistenceAdapter,
			flush
		};
		$[30] = flush;
		$[31] = register;
		$[32] = setDefState;
		$[33] = setPersistenceAdapter;
		$[34] = t19;
		$[35] = t20;
	} else t20 = $[35];
	return t20;
};
/**
* @deprecated Since 2026-06-14 — migrate to the Unstable / Experimental API.
* Scheduled for removal on/after 2026-09-14. See
* {@link https://www.assistant-ui.com/docs/tools/interactables#migrating-from-the-previous-api | Interactables migration guide}.
*/
const Interactables = resource(useInteractables);
attachTransformScopes$1(useInteractables, (scopes, parent) => {
	if (!scopes.modelContext && parent.modelContext.source === null) scopes.modelContext = ModelContext();
});
function _temp() {
	return {
		definitions: nullProtoRecord(),
		persistence: nullProtoRecord()
	};
}
//#endregion
export { Interactables };
