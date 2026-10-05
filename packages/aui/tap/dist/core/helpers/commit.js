import { throwAggregated } from "./throwAggregated.js";
import { depsShallowEqual } from "../../hooks/utils/depsShallowEqual.js";
//#region src/core/helpers/commit.ts
function commitAllCallbacks(callbacks) {
	if (callbacks.length === 0) return;
	let errors;
	for (let i = 0; i < callbacks.length; i++) try {
		callbacks[i]();
	} catch (error) {
		(errors ??= []).push(error);
	}
	if (errors !== void 0) throwAggregated(errors, "Errors during commit");
}
function setupEffect(cell) {
	const setup = cell.setup;
	const deps = cell.setupDeps;
	const generation = cell.generation;
	let cleanup;
	try {
		const result = setup();
		if (result !== void 0 && typeof result !== "function") throw new Error(`An effect function must either return a cleanup function or nothing. Received: ${typeof result}`);
		cleanup = result;
	} finally {
		if (cell.generation === generation) {
			cell.cleanup = cleanup;
			cell.deps = deps;
		} else cleanup?.();
	}
}
const effectNeedsRun = (cell) => {
	if (cell.setup === void 0) return false;
	if (cell.deps === null) return true;
	if (cell.setupDeps === void 0) return true;
	return !depsShallowEqual(cell.deps, cell.setupDeps);
};
function reconcileCells(cells, errors) {
	let pending;
	for (const cell of cells) if (effectNeedsRun(cell)) (pending ??= []).push(cell);
	if (pending === void 0) return errors;
	for (const cell of pending) {
		cell.deps = null;
		if (cell.cleanup === void 0) continue;
		try {
			cell.cleanup();
		} catch (e) {
			(errors ??= []).push(e);
		} finally {
			cell.cleanup = void 0;
		}
	}
	for (const cell of pending) try {
		setupEffect(cell);
	} catch (e) {
		(errors ??= []).push(e);
	}
	return errors;
}
function reconcileEffects(fiber, includeInsertion = true) {
	let errors;
	if (fiber.insertionCells !== null && includeInsertion) errors = reconcileCells(fiber.insertionCells, errors);
	errors = reconcileCells(fiber.effectCells, errors);
	if (errors !== void 0) throwAggregated(errors, "Errors during commit");
}
function cleanupCells(cells) {
	let errors;
	for (const cell of cells) {
		cell.deps = null;
		if (cell.cleanup) try {
			cell.cleanup?.();
		} catch (e) {
			(errors ??= []).push(e);
		} finally {
			cell.cleanup = void 0;
		}
	}
	if (errors !== void 0) throwAggregated(errors, "Errors during cleanup");
}
//#endregion
export { cleanupCells, commitAllCallbacks, reconcileEffects };
