import { isJSONValue, isRecord } from "../utils/json/is-json.js";
import { isJSONValueEqual } from "../utils/json/is-json-equal.js";
//#region src/model-context/interactable-composer-metadata.ts
/**
* Reads the interactable snapshots stamped on a message's
* `metadata.custom.interactables`, or `undefined` if none. This is the read
* half of the snapshot channel — integrations use it to surface interactable
* state to the model (see `unstable_injectInteractableContext` in
* `@assistant-ui/ai-sdk` for the AI SDK implementation).
*
* @deprecated Unstable / Experimental (not actually removed).
*/
function unstable_getInteractableSnapshots(message) {
	const metadata = message.metadata;
	if (!metadata || typeof metadata !== "object") return void 0;
	const custom = metadata.custom;
	if (!custom || typeof custom !== "object") return void 0;
	const items = custom.interactables;
	return Array.isArray(items) ? items : void 0;
}
/**
* Canonical model-facing wording for one snapshot entry.
*
* @deprecated Unstable / Experimental (not actually removed).
*/
function unstable_formatInteractableSnapshot(entry) {
	if (entry.partial) return `[State of "${entry.name}" (id: ${JSON.stringify(entry.id)}) changed — updated fields: ${JSON.stringify(entry.state)}; fields not listed are unchanged]`;
	return `[Current state of "${entry.name}" (id: ${JSON.stringify(entry.id)}): ${JSON.stringify(entry.state)}]`;
}
/** The model-facing tool name for an interactable `name`. One tool per name. */
function interactableToolName(name) {
	return `update_${name.replace(/[^a-zA-Z0-9_-]/g, "_")}`;
}
const getArrayItemId = (item) => {
	if (!isRecord(item)) return void 0;
	const id = item.id;
	return typeof id === "string" || typeof id === "number" ? id : void 0;
};
/**
* Overlays a streamed `value` onto `prev` along the parser's `partialPath`:
* the record still being written keeps the fields of `prev` it has not
* reached yet, while every field the parser has closed replaces its previous
* value, as the final merge will.
*/
function overlayPartialPath(prev, value, partialPath = []) {
	if (!isRecord(prev) || !isRecord(value)) return value;
	const next = {
		...prev,
		...value
	};
	const [key, ...rest] = partialPath;
	if (key !== void 0 && Object.hasOwn(value, key)) next[key] = overlayPartialPath(prev[key], value[key], rest);
	return next;
}
function applyArrayUpdate(prev, update, mintId, partialPath) {
	let next = Array.isArray(update.set) ? [...update.set] : [...prev];
	if (update.clear === true) next = [];
	if (Array.isArray(update.remove) && update.remove.length > 0) {
		const ids = new Set(update.remove);
		next = next.filter((item) => {
			const id = getArrayItemId(item);
			return id !== void 0 ? !ids.has(id) : !ids.has(item);
		});
	}
	const patches = update.update;
	if (Array.isArray(patches) && patches.length > 0) {
		const patchesById = /* @__PURE__ */ new Map();
		for (const candidate of patches) {
			const id = getArrayItemId(candidate);
			if (id !== void 0 && !Number.isNaN(id) && !patchesById.has(id)) patchesById.set(id, candidate);
		}
		const streaming = partialPath?.[0] === "update" ? {
			patch: patches[Number(partialPath[1])],
			rest: partialPath.slice(2)
		} : void 0;
		next = next.map((item) => {
			const id = getArrayItemId(item);
			if (id === void 0 || !isRecord(item)) return item;
			const patch = patchesById.get(id);
			if (!patch) return item;
			return streaming && patch === streaming.patch ? overlayPartialPath(item, patch, streaming.rest) : {
				...item,
				...patch
			};
		});
	}
	if (Array.isArray(update.add) && update.add.length > 0) {
		const added = mintId ? update.add.map((item) => {
			if (!isRecord(item) || item.id !== void 0) return item;
			const id = mintId();
			return id === void 0 ? item : {
				...item,
				id
			};
		}) : update.add;
		next = [...next, ...added];
	}
	return next;
}
/**
* The merge `update_*` tools apply: top-level keys replace, rest preserved.
* Array fields also accept operation objects (`add`, `update`, `remove`,
* `clear`, `set`) so collection edits do not need a companion manage_* tool.
*/
function shallowMergeInteractableState(prev, partial, options) {
	if (!isRecord(prev) || !isRecord(partial)) return partial;
	const baseline = isRecord(options?.arrayBaseline) ? options.arrayBaseline : prev;
	const partialPath = options?.partialPath;
	const next = Object.entries(prev);
	for (const [key, value] of Object.entries(partial)) {
		const baseValue = baseline[key];
		const streamingPath = partialPath?.[0] === key ? partialPath.slice(1) : void 0;
		if (Array.isArray(baseValue) && isRecord(value)) {
			const mintId = options?.idFactory && (options.idKeyedFields === void 0 || options.idKeyedFields.has(key)) ? () => options.idFactory?.(key) : void 0;
			next.push([key, applyArrayUpdate(baseValue, value, mintId, streamingPath)]);
		} else if (streamingPath) next.push([key, overlayPartialPath(prev[key], value, streamingPath)]);
		else next.push([key, value]);
	}
	return Object.fromEntries(next);
}
/**
* The top-level fields of `next` that differ from `known`, for stamping a
* partial snapshot. Returns `undefined` when a partial stamp has no benefit:
* the change is not expressible as a shallow merge (non-object states, or a
* top-level key was removed), or every field changed anyway — the caller
* falls back to a full snapshot.
*/
function shallowDiffInteractableState(known, next) {
	if (!isRecord(known) || !isRecord(next)) return void 0;
	for (const key of Object.keys(known)) if (!Object.hasOwn(next, key)) return void 0;
	const diff = [];
	for (const [key, value] of Object.entries(next)) if (!Object.hasOwn(known, key) || !isJSONValueEqual(known[key], value)) diff.push([key, value]);
	const changed = diff.length;
	if (changed === 0 || changed === Object.keys(next).length) return void 0;
	return Object.fromEntries(diff);
}
const asToolCallPart = (part) => {
	if (!part || typeof part !== "object") return void 0;
	const p = part;
	return p.type === "tool-call" ? p : void 0;
};
/** Whether an accepted `update_*` call addressed instance `id`. */
const updateCallTargets = (p, id) => {
	if (!p.args || typeof p.args !== "object") return false;
	const result = isRecord(p.result) ? p.result : void 0;
	if (result?.success === false) return false;
	if (typeof result?.id === "string") return result.id === id;
	const argsId = p.args.id;
	return argsId === id || argsId === void 0;
};
const createAddedItemIdFactory = (result) => {
	const value = isRecord(result) ? result.addedItemIds : void 0;
	if (!isRecord(value)) return void 0;
	const idsByField = /* @__PURE__ */ new Map();
	for (const [field, ids] of Object.entries(value)) {
		if (!Array.isArray(ids)) continue;
		const stringIds = ids.filter((item) => typeof item === "string");
		if (stringIds.length > 0) idsByField.set(field, stringIds);
	}
	if (idsByField.size === 0) return void 0;
	return (field) => idsByField.get(field)?.shift();
};
const versionsCache = /* @__PURE__ */ new WeakMap();
/**
* Every version of interactable `id` recorded in the thread, oldest first,
* folded chronologically:
*
* - the tool call whose `toolCallId` equals `id` seeds the baseline with its
*   args (`origin: "create"`) — the `id: toolCallId` convention for
*   tool-created interactables,
* - a snapshot stamped on a user message is a `"user-edit"` version (a full
*   snapshot replaces the state; a partial one shallow-merges),
* - each accepted `update_*` call shallow-merges an `"update"` version.
*
* The last entry is the state the model knows. Partial snapshots and update
* calls with no baseline to merge into are skipped.
*
* @deprecated Unstable / Experimental (not actually removed).
*/
function unstable_getInteractableVersions(messages, id, name) {
	let byName = versionsCache.get(messages);
	if (!byName) {
		byName = /* @__PURE__ */ new Map();
		versionsCache.set(messages, byName);
	}
	let byId = byName.get(name);
	if (!byId) {
		byId = /* @__PURE__ */ new Map();
		byName.set(name, byId);
	}
	const cached = byId.get(id);
	if (cached) return cached;
	const toolName = interactableToolName(name);
	const versions = [];
	const current = () => versions[versions.length - 1];
	for (const msg of messages) {
		if (msg.role === "user") {
			const entry = unstable_getInteractableSnapshots(msg)?.find((it) => it.id === id);
			if (!entry) continue;
			if (entry.partial) {
				const prev = current();
				if (prev) versions.push({
					state: shallowMergeInteractableState(prev.state, entry.state),
					origin: "user-edit"
				});
			} else versions.push({
				state: entry.state,
				origin: "user-edit"
			});
			continue;
		}
		if (msg.role !== "assistant") continue;
		for (const part of msg.content ?? []) {
			const p = asToolCallPart(part);
			if (!p) continue;
			if (p.toolCallId === id && p.toolName === name) {
				if (p.args && typeof p.args === "object") versions.push({
					state: p.args,
					origin: "create",
					toolCallId: id
				});
			} else if (p.toolName === toolName && updateCallTargets(p, id)) {
				const prev = current();
				if (prev) {
					const { id: _id, ...partial } = p.args;
					const idFactory = createAddedItemIdFactory(p.result);
					versions.push({
						state: idFactory ? shallowMergeInteractableState(prev.state, partial, { idFactory }) : shallowMergeInteractableState(prev.state, partial),
						origin: "update",
						toolCallId: p.toolCallId
					});
				}
			}
		}
	}
	byId.set(id, versions);
	return versions;
}
/**
* The state the model knows for interactable `id` — its latest recorded
* version, or `undefined` when no baseline exists yet.
*/
function findModelKnownState(messages, id, name) {
	const versions = unstable_getInteractableVersions(messages, id, name);
	const last = versions[versions.length - 1];
	return last ? { state: last.state } : void 0;
}
/**
* Snapshot gate. Stamps an interactable only when the model doesn't already
* know its state (no baseline yet, or the live state differs from the folded
* thread record). A change that fits a shallow merge is stamped as a partial
* snapshot carrying just the changed fields; otherwise the full state is
* stamped. Other metadata keys pass through untouched.
*/
function gateInteractableComposerMetadata(meta, messages) {
	if (!meta) return void 0;
	const { interactables, ...rest } = meta;
	const gated = { ...rest };
	if (Array.isArray(interactables)) {
		const pending = [];
		for (const it of interactables) {
			if (process.env.NODE_ENV !== "production" && !isJSONValue(it.state)) console.warn(`[Interactables] state for "${it.name}" (${it.id}) is not JSON-equatable (an undefined, NaN, Infinity, function, or symbol value?). It will be re-snapshotted on every send, recreating per-message growth. Use plain JSON values.`);
			const known = findModelKnownState(messages, it.id, it.name);
			if (!known) {
				pending.push({
					id: it.id,
					name: it.name,
					state: it.state
				});
				continue;
			}
			if (isJSONValueEqual(it.state, known.state)) continue;
			const diff = shallowDiffInteractableState(known.state, it.state);
			pending.push(diff ? {
				id: it.id,
				name: it.name,
				state: diff,
				partial: true
			} : {
				id: it.id,
				name: it.name,
				state: it.state
			});
		}
		if (pending.length) gated.interactables = pending;
	}
	return Object.keys(gated).length ? gated : void 0;
}
//#endregion
export { findModelKnownState, gateInteractableComposerMetadata, interactableToolName, overlayPartialPath, shallowMergeInteractableState, unstable_formatInteractableSnapshot, unstable_getInteractableSnapshots, unstable_getInteractableVersions };
