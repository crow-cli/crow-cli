//#region src/runtimes/remote-thread-list/title-generation.ts
function getThreadTitleState(states, threadId) {
	let state = states.get(threadId);
	if (state === void 0) {
		state = {
			generations: /* @__PURE__ */ new Set(),
			pendingClaim: null,
			inFlightClaims: /* @__PURE__ */ new Set(),
			manualTitle: void 0,
			latestExplicit: null,
			nextOrder: 0
		};
		states.set(threadId, state);
	}
	return state;
}
function pruneThreadTitleState(states, threadId, state) {
	if (state.generations.size === 0 && state.pendingClaim === null && state.inFlightClaims.size === 0 && state.manualTitle === void 0 && states.get(threadId) === state) states.delete(threadId);
}
function isCurrentGeneration(state, generation) {
	return !generation.superseded && (state.latestExplicit?.order ?? 0) <= generation.order;
}
function isCurrentClaim(state, claim) {
	return (state.latestExplicit?.order ?? 0) < claim.order;
}
function startThreadTitleRename(states, threadId, title) {
	const state = getThreadTitleState(states, threadId);
	let settle;
	const settled = new Promise((resolve) => {
		settle = resolve;
	});
	const claim = {
		title,
		order: ++state.nextOrder,
		settled,
		settle
	};
	state.pendingClaim = claim;
	state.inFlightClaims.add(claim);
	for (const generation of state.generations) if (generation.order < claim.order) generation.claim = claim;
	return claim;
}
function finishThreadTitleRename(states, threadId, claim, renamed) {
	claim.settle(renamed);
	const state = states.get(threadId);
	if (state === void 0) return;
	state.inFlightClaims.delete(claim);
	if (state.pendingClaim === claim) {
		state.pendingClaim = null;
		if (renamed) state.manualTitle = claim.title;
	}
	pruneThreadTitleState(states, threadId, state);
}
function takeManualTitle(states, threadId, state) {
	const retained = state.manualTitle;
	if (retained === void 0) return void 0;
	state.manualTitle = void 0;
	pruneThreadTitleState(states, threadId, state);
	return retained;
}
function clearThreadTitleState(states, threadId) {
	states.delete(threadId);
}
function startThreadTitleGeneration(states, threadId, automatic) {
	const state = getThreadTitleState(states, threadId);
	if (automatic && state.pendingClaim === null && takeManualTitle(states, threadId, state) !== void 0) return null;
	let settlePersisted;
	const persisted = new Promise((resolve) => {
		settlePersisted = resolve;
	});
	const generation = {
		automatic,
		order: ++state.nextOrder,
		claim: automatic ? state.pendingClaim : null,
		beforeGenerationClaims: automatic ? [] : [...state.inFlightClaims],
		superseded: false,
		persisted,
		settlePersisted
	};
	if (!automatic) {
		state.pendingClaim = null;
		state.manualTitle = void 0;
		state.latestExplicit = generation;
		for (const active of state.generations) if (active.automatic) active.superseded = true;
	}
	state.generations.add(generation);
	return generation;
}
/**
* Runs one title generation under the per-thread rename claims and generation
* ordering, so the title that wins locally is also the title left on the
* server.
*
* A generated run persists the title itself, and the adapter exposes no
* compare-and-set, so the run that loses reasserts the winner through `rename`
* only after `generate` has resolved. Reasserting mid-stream would race the
* run's own write and lose the winning title on the server.
*/
async function runThreadTitleGeneration({ states, threadId, automatic, generate, rename, applyTitle }) {
	const state = getThreadTitleState(states, threadId);
	const generation = startThreadTitleGeneration(states, threadId, automatic);
	if (generation === null) return;
	let persistedTitle;
	let persistedOrder = generation.order;
	const settleClaim = async (claim) => {
		const renamed = await claim.settled;
		if (generation.claim !== claim) return void 0;
		if (!renamed) {
			generation.claim = null;
			if (state.pendingClaim === claim) state.pendingClaim = null;
		}
		return renamed;
	};
	const retainManualTitle = () => automatic && takeManualTitle(states, threadId, state) !== void 0;
	const repairLostRace = async () => {
		if (persistedTitle === void 0) return;
		while (true) {
			const claim = generation.claim;
			if (claim !== null && claim.order > persistedOrder && isCurrentClaim(state, claim)) {
				if (await settleClaim(claim) === true) {
					persistedTitle = claim.title;
					persistedOrder = claim.order;
					await rename(claim.title);
				}
				continue;
			}
			const winner = state.latestExplicit;
			if (winner === null || winner.order <= persistedOrder) return;
			const title = await winner.persisted;
			if (state.latestExplicit !== winner) continue;
			persistedOrder = winner.order;
			if (title === void 0 || title === persistedTitle) return;
			persistedTitle = title;
			await rename(title);
		}
	};
	const runGeneration = async () => {
		if (generation.beforeGenerationClaims.length > 0) await Promise.all(generation.beforeGenerationClaims.map((claim) => claim.settled));
		if (generation.claim !== null) {
			const renamed = await settleClaim(generation.claim);
			if (renamed === true) {
				generation.superseded = true;
				return;
			}
			if (renamed === false && retainManualTitle()) return;
		}
		if (!isCurrentGeneration(state, generation)) return;
		let sawTitle = false;
		let lastTitle;
		await generate(async (title) => {
			sawTitle = true;
			lastTitle = title;
			if (title !== void 0) persistedTitle = title;
			const claim = generation.claim;
			if (claim !== null) {
				if (await settleClaim(claim) !== false) return;
				if (retainManualTitle()) {
					generation.superseded = true;
					return;
				}
			}
			if (isCurrentGeneration(state, generation)) await applyTitle(lastTitle);
		});
		while (true) {
			const claim = generation.claim;
			if (claim === null) return;
			const renamed = await settleClaim(claim);
			if (renamed === void 0) continue;
			if (renamed === false) {
				if (retainManualTitle()) return;
				if (sawTitle && isCurrentGeneration(state, generation)) await applyTitle(lastTitle);
				return;
			}
			if (!isCurrentClaim(state, claim)) return;
			await rename(claim.title);
			persistedTitle = claim.title;
			persistedOrder = claim.order;
			if (generation.claim !== claim) continue;
			if (!isCurrentGeneration(state, generation)) return;
			await applyTitle(claim.title);
			generation.superseded = true;
			return;
		}
	};
	try {
		await runGeneration();
		await repairLostRace();
	} finally {
		generation.settlePersisted(persistedTitle);
		state.generations.delete(generation);
		pruneThreadTitleState(states, threadId, state);
	}
}
//#endregion
export { clearThreadTitleState, finishThreadTitleRename, runThreadTitleGeneration, startThreadTitleRename };
