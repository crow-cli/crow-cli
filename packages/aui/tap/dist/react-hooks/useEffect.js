import { getCurrentResourceFiber } from "../core/helpers/execution-context.js";
import { addCommit } from "../core/helpers/root.js";
import { throwHookOrderChanged, throwRenderedMoreHooks } from "./utils/hookErrors.js";
//#region src/react-hooks/useEffect.ts
const newEffect = (type) => ({
	type,
	setup: void 0,
	setupDeps: void 0,
	cleanup: void 0,
	deps: null,
	generation: 0
});
function useEffectImpl(effect, deps, type) {
	const fiber = getCurrentResourceFiber();
	const index = fiber.currentIndex++;
	const existing = fiber.cells[index];
	const cell = existing === void 0 ? newEffect(type) : existing.type === type ? existing : throwHookOrderChanged();
	if (existing === void 0) {
		if (!fiber.isFirstRender) throwRenderedMoreHooks();
		fiber.cells[index] = cell;
		if (type === "insertion") (fiber.insertionCells ??= []).push(cell);
		else fiber.effectCells.push(cell);
	}
	if (cell.deps !== null && !!deps !== !!cell.deps) throw new Error("useEffect called with and without dependencies across re-renders");
	const isRefreshing = fiber.isRefreshing;
	addCommit(fiber, () => {
		cell.setup = effect;
		cell.setupDeps = deps;
		if (isRefreshing) cell.deps = null;
		cell.generation++;
	});
}
function useEffect(effect, deps) {
	useEffectImpl(effect, deps, "effect");
}
//#endregion
export { useEffect, useEffectImpl };
