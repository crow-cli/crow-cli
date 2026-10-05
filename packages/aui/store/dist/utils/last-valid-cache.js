//#region src/utils/last-valid-cache.ts
const EMPTY = Symbol("last-valid-cache.empty");
/**
* Guards a positional or id-addressed scope resolution across a collection shrink. The scope
* re-resolves inside the store notification, before the binding's queued
* render can unmount it, so a shrink briefly reads out of bounds; `resolve`
* serves the last valid item for exactly that window. Every stale serve
* schedules an expiry through `scheduleExpiry` carrying the generation it
* observed: a valid resolution in between advances the generation and voids
* the pending expiry, while a provider still mounted out of bounds after the
* flush has its cache dropped and `reportStale` run once (its next resolution
* then throws, like a never-valid index does immediately). The expiry only
* drops the cache; descendants keep the last committed state until the next
* store notification re-resolves the scope. `scheduleExpiry` runs its
* callback after the binding's current render flush settles (Vue's
* `nextTick`, for example). Pass `reportStale: null` when a sibling cache
* over the same validity predicate already reports.
*/
const createLastValidCache = (reportStale, scheduleExpiry) => {
	let last = EMPTY;
	let generation = 0;
	const expire = () => {
		const scheduledAt = generation;
		scheduleExpiry(() => {
			if (generation !== scheduledAt) return;
			if (last === EMPTY) return;
			last = EMPTY;
			reportStale?.();
		});
	};
	return { resolve: (valid, resolveItem) => {
		if (valid) {
			generation++;
			last = resolveItem();
			return last;
		}
		if (last !== EMPTY) expire();
		return last === EMPTY ? resolveItem() : last;
	} };
};
/**
* The standard `reportStale` callback for a by-index or by-id provider: skipped when
* the provider is disposed or its props moved on, re-checked against the live
* collection (an unavailable parent scope counts as still stale), and logged
* through `console.error` so the misuse is visible where the subsequent
* throw may not be.
*/
const createStaleReporter = (options) => () => {
	if (!options.isCurrent()) return;
	try {
		if (options.isValid()) return;
	} catch {}
	console.error(typeof options.index === "string" ? `${options.name}: id "${options.index}" is no longer present after the update settled; the scope throws on its next resolution.` : `${options.name}: index ${options.index} is still out of bounds after the update settled; the scope throws on its next resolution.`);
};
//#endregion
export { createLastValidCache, createStaleReporter };
