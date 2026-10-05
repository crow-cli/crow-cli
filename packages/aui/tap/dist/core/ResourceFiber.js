import { peekResourceFiber, withResourceFiber } from "./helpers/execution-context.js";
import { isDevelopment } from "./helpers/env.js";
import { commitRoot } from "./helpers/root.js";
import { bubbleContextDeps } from "./context.js";
import { throwAggregated } from "./helpers/throwAggregated.js";
import { cleanupCells, commitAllCallbacks, reconcileEffects } from "./helpers/commit.js";
import { withReactDispatcher } from "./react-dispatcher.js";
//#region src/core/ResourceFiber.ts
function createResourceFiber(hook, root, markDirty = void 0, strictMode) {
	return {
		hook,
		root,
		markDirty,
		devStrictMode: strictMode,
		cells: [],
		effectCells: [],
		insertionCells: null,
		hostCells: null,
		contextDeps: null,
		wipContextDeps: null,
		wipCommitCallbacks: null,
		memoCache: {
			current: null,
			workInProgress: null,
			refreshedIndices: null,
			index: 0
		},
		renderPendingCells: null,
		currentIndex: 0,
		isRefreshing: false,
		isFirstRender: true,
		isMounted: false,
		isReleased: false,
		isNeverMounted: true
	};
}
function discardWipRender(fiber) {
	fiber.wipCommitCallbacks = null;
	fiber.wipContextDeps = null;
	fiber.memoCache.workInProgress = null;
	fiber.memoCache.refreshedIndices = null;
}
function cleanupResourceFiber(fiber, insertion, errors) {
	try {
		if (insertion) {
			fiber.isReleased = true;
			if (fiber.insertionCells !== null) cleanupCells(fiber.insertionCells);
		} else if (fiber.isMounted) {
			fiber.isMounted = false;
			cleanupCells(fiber.effectCells);
		}
	} catch (error) {
		(errors ??= []).push(error);
	}
	if (fiber.hostCells !== null) for (const cell of fiber.hostCells) {
		if (cell.fiber !== null) errors = cleanupResourceFiber(cell.fiber, insertion, errors);
		if (cell.fibers !== null) for (const { fiber } of cell.fibers.values()) errors = cleanupResourceFiber(fiber, insertion, errors);
	}
	return errors;
}
function unmountResourceFiber(fiber, permanent = true) {
	let errors;
	if (permanent) errors = cleanupResourceFiber(fiber, true, errors);
	errors = cleanupResourceFiber(fiber, false, errors);
	if (errors !== void 0) throwAggregated(errors, "Errors during cleanup");
}
function unmountResourceFibers(fibers) {
	let errors;
	for (const fiber of fibers) if (fiber.isReleased) errors = cleanupResourceFiber(fiber, true, errors);
	for (const fiber of fibers) errors = cleanupResourceFiber(fiber, false, errors);
	if (errors !== void 0) throwAggregated(errors, "Errors during cleanup");
}
function renderResourceFiber(fiber, args) {
	if (fiber.renderPendingCells !== null) {
		for (const cell of fiber.renderPendingCells) cell.renderQueue = null;
		fiber.renderPendingCells.clear();
	}
	let passes = 0;
	let value;
	const wasRefreshing = fiber.isRefreshing;
	fiber.isRefreshing = wasRefreshing || (peekResourceFiber()?.isRefreshing ?? false);
	try {
		do {
			if (++passes > 25) throw new Error("Too many re-renders. tap limits the number of renders to prevent an infinite loop.");
			fiber.memoCache.index = 0;
			withResourceFiber(fiber, () => {
				value = withReactDispatcher(() => fiber.hook(...args));
			});
		} while ((fiber.renderPendingCells?.size ?? 0) > 0);
	} catch (error) {
		discardWipRender(fiber);
		throw error;
	} finally {
		fiber.isRefreshing = wasRefreshing;
	}
	bubbleContextDeps(fiber);
	return value;
}
function commitResourceFiber(fiber) {
	const commitCallbacks = fiber.wipCommitCallbacks;
	fiber.wipCommitCallbacks = null;
	const strictReplay = isDevelopment && !fiber.isMounted && fiber.devStrictMode === "root";
	fiber.isMounted = true;
	fiber.isNeverMounted = false;
	if (commitCallbacks !== null) {
		fiber.contextDeps = fiber.wipContextDeps;
		commitRoot(fiber.root);
		if (fiber.memoCache.workInProgress !== null) {
			fiber.memoCache.current = fiber.memoCache.workInProgress;
			fiber.memoCache.workInProgress = null;
			fiber.memoCache.refreshedIndices = null;
		}
		commitAllCallbacks(commitCallbacks);
	}
	if (strictReplay) {
		reconcileEffects(fiber, commitCallbacks !== null);
		unmountResourceFiber(fiber, false);
		fiber.isMounted = true;
	}
	reconcileEffects(fiber, !strictReplay && commitCallbacks !== null);
}
//#endregion
export { commitResourceFiber, createResourceFiber, discardWipRender, renderResourceFiber, unmountResourceFiber, unmountResourceFibers };
