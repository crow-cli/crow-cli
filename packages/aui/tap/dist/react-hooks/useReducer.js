import { getCurrentResourceFiber, peekResourceFiber } from "../core/helpers/execution-context.js";
import { isDevelopment } from "../core/helpers/env.js";
import { addCommit, applyChangelogRecord, markReducerDirty } from "../core/helpers/root.js";
import { throwHookOrderChanged, throwRenderedMoreHooks } from "./utils/hookErrors.js";
//#region src/react-hooks/useReducer.ts
const dispatchOnFiber = (fiber, record, eagerReducer) => {
	if (fiber.isNeverMounted) throw new Error("Resource updated before mount");
	let evaluated = false;
	let hasWork = true;
	fiber.root.unsettledCount++;
	fiber.root.dispatchUpdate(() => {
		if (evaluated) return hasWork;
		evaluated = true;
		if (eagerReducer && fiber.root.changelog.length === 0 && !record.cell.isDirty && !record.hasEagerState) {
			record.prevState = record.cell.workInProgress;
			record.eagerState = eagerReducer(record.cell.workInProgress, record.action);
			record.hasEagerState = true;
			hasWork = !Object.is(record.cell.current, record.eagerState);
			if (!hasWork && !record.settled) {
				record.settled = true;
				fiber.root.unsettledCount--;
			}
		}
		return hasWork;
	}, () => {
		evaluated = true;
		hasWork = true;
		applyChangelogRecord(record);
		if (!record.logged) {
			record.logged = true;
			fiber.root.changelog.push(record);
		}
		return true;
	});
};
const createReducerCell = (fiber, reducer, initialArg, initFn, eagerBailout) => {
	const initialState = initFn ? initFn(initialArg) : initialArg;
	if (isDevelopment && fiber.devStrictMode && initFn) initFn(initialArg);
	const cell = {
		type: "reducer",
		workInProgress: initialState,
		current: initialState,
		isDirty: false,
		queue: null,
		renderQueue: null,
		reducer,
		dispatch: (action) => {
			const currentFiber = peekResourceFiber();
			if (currentFiber !== null) {
				if (currentFiber !== fiber) throw new Error("Cannot update a resource while rendering a different resource.");
				(fiber.renderPendingCells ??= /* @__PURE__ */ new Set()).add(cell);
				(cell.renderQueue ??= []).push(action);
			} else {
				const record = {
					fiber,
					cell,
					action,
					hasEagerState: false,
					eagerState: void 0,
					prevState: cell.current,
					settled: false,
					queued: false,
					logged: false
				};
				dispatchOnFiber(fiber, record, eagerBailout ? reducer : void 0);
			}
		}
	};
	return cell;
};
function useReducerImpl(reducer, initialArg, initFn, eagerBailout) {
	const fiber = getCurrentResourceFiber();
	const index = fiber.currentIndex++;
	const existing = fiber.cells[index];
	const cell = (() => {
		if (existing !== void 0) return existing.type === "reducer" ? existing : throwHookOrderChanged();
		if (!fiber.isFirstRender) throwRenderedMoreHooks();
		const cell = createReducerCell(fiber, reducer, initialArg, initFn, eagerBailout);
		fiber.cells[index] = cell;
		return cell;
	})();
	const queue = cell.queue;
	if (queue !== null) {
		const sameReducer = reducer === cell.reducer;
		for (let i = 0; i < queue.length; i++) {
			const item = queue[i];
			if (!item.hasEagerState || !sameReducer || !Object.is(item.prevState, cell.workInProgress)) {
				item.prevState = cell.workInProgress;
				item.eagerState = reducer(cell.workInProgress, item.action);
				item.hasEagerState = true;
				if (isDevelopment && fiber.devStrictMode) item.eagerState = reducer(cell.workInProgress, item.action);
			} else if (isDevelopment && fiber.devStrictMode) reducer(cell.workInProgress, item.action);
			item.queued = false;
			cell.workInProgress = item.eagerState;
		}
		cell.queue = null;
	}
	cell.reducer = reducer;
	if (cell.renderQueue !== null) {
		let derived = cell.workInProgress;
		for (const action of cell.renderQueue) derived = reducer(derived, action);
		cell.renderQueue = null;
		fiber.renderPendingCells?.delete(cell);
		if (!Object.is(derived, cell.workInProgress)) {
			markReducerDirty(fiber, cell);
			cell.workInProgress = derived;
		}
	}
	if (cell.isDirty) addCommit(fiber, () => {
		cell.current = cell.workInProgress;
		cell.isDirty = false;
	});
	return [cell.workInProgress, cell.dispatch];
}
function useReducer(reducer, initialArg, init) {
	return useReducerImpl(reducer, initialArg, init, false);
}
//#endregion
export { useReducer, useReducerImpl };
