import { getCurrentResourceFiber } from "../core/helpers/execution-context.js";
import { isDevelopment } from "../core/helpers/env.js";
import { addRollback } from "../core/helpers/root.js";
//#region src/react-hooks/useMemoCache.ts
const MEMO_CACHE_SENTINEL = Symbol.for("react.memo_cache_sentinel");
const createMemoCache = (size) => new Array(size).fill(MEMO_CACHE_SENTINEL);
const nextFiberMemoCache = (fiber, size) => {
	const memoCache = fiber.memoCache;
	let data = memoCache.workInProgress;
	if (data === null) {
		const current = memoCache.current;
		data = current === null ? [] : current.map((array) => array.slice());
		memoCache.workInProgress = data;
		addRollback(fiber.root, () => {
			memoCache.workInProgress = null;
			memoCache.refreshedIndices = null;
		});
	}
	const index = memoCache.index++;
	let cache = data[index];
	if (memoCache.refreshedIndices?.has(index) && !fiber.isRefreshing) {
		memoCache.refreshedIndices.delete(index);
		cache = memoCache.current?.[index]?.slice() ?? createMemoCache(size);
		data[index] = cache;
	}
	if (cache === void 0 || fiber.isRefreshing) {
		cache = createMemoCache(size);
		data[index] = cache;
		if (fiber.isRefreshing) (memoCache.refreshedIndices ??= /* @__PURE__ */ new Set()).add(index);
	} else if (isDevelopment && cache.length !== size) console.error(`Expected a constant size argument for each invocation of c(). The previous cache was allocated with size ${cache.length} but size ${size} was requested.`);
	return cache;
};
const useMemoCache = (size) => nextFiberMemoCache(getCurrentResourceFiber(), size);
//#endregion
export { MEMO_CACHE_SENTINEL, createMemoCache, useMemoCache };
