import { getCurrentResourceFiber } from "../core/helpers/execution-context.js";
import { isDevelopment } from "../core/helpers/env.js";
import { addCommit, addRollback } from "../core/helpers/root.js";
import { throwHookOrderChanged, throwRenderedMoreHooks } from "./utils/hookErrors.js";
import { depsShallowEqual } from "../hooks/utils/depsShallowEqual.js";
//#region src/react-hooks/useMemo.ts
const addMemoCommit = (fiber, cell) => {
	addCommit(fiber, () => {
		cell.current = cell.wip;
		cell.currentDeps = cell.wipDeps;
		cell.wipIsRefreshing = false;
		cell.isDirty = false;
	});
};
const useMemo = (fn, deps) => {
	const fiber = getCurrentResourceFiber();
	const index = fiber.currentIndex++;
	let cell = fiber.cells[index];
	if (cell === void 0) {
		if (!fiber.isFirstRender) throwRenderedMoreHooks();
		const value = fn();
		if (isDevelopment && fiber.devStrictMode) fn();
		cell = {
			type: "memo",
			current: value,
			currentDeps: deps,
			wip: value,
			wipDeps: deps,
			wipIsRefreshing: false,
			isDirty: false
		};
		fiber.cells[index] = cell;
		return value;
	}
	if (cell.type !== "memo") throwHookOrderChanged();
	const memoCell = cell;
	if (memoCell.wipIsRefreshing && !fiber.isRefreshing) {
		memoCell.wip = memoCell.current;
		memoCell.wipDeps = memoCell.currentDeps;
		memoCell.wipIsRefreshing = false;
		memoCell.isDirty = false;
	}
	if (!fiber.isRefreshing && depsShallowEqual(memoCell.wipDeps, deps)) {
		if (memoCell.isDirty) addMemoCommit(fiber, memoCell);
		return memoCell.wip;
	}
	const value = fn();
	if (isDevelopment && fiber.devStrictMode) fn();
	memoCell.wip = value;
	memoCell.wipDeps = deps;
	memoCell.wipIsRefreshing = fiber.isRefreshing;
	if (!memoCell.isDirty) {
		memoCell.isDirty = true;
		addRollback(fiber.root, () => {
			memoCell.wip = memoCell.current;
			memoCell.wipDeps = memoCell.currentDeps;
			memoCell.wipIsRefreshing = false;
			memoCell.isDirty = false;
		});
	}
	addMemoCommit(fiber, memoCell);
	return value;
};
//#endregion
export { useMemo };
