import { getCurrentResourceFiber } from "../core/helpers/execution-context.js";
import { addCommit } from "../core/helpers/root.js";
import { throwHookOrderChanged, throwRenderedMoreHooks } from "./utils/hookErrors.js";
//#region src/react-hooks/useRefreshScope.ts
function useRefreshScope(token, fn) {
	const fiber = getCurrentResourceFiber();
	const index = fiber.currentIndex++;
	let cell = fiber.cells[index];
	if (cell === void 0) {
		if (!fiber.isFirstRender) throwRenderedMoreHooks();
		cell = {
			type: "refresh",
			token,
			isCommitted: false
		};
		fiber.cells[index] = cell;
	}
	if (cell.type !== "refresh") return throwHookOrderChanged();
	const refreshCell = cell;
	const isRefreshing = refreshCell.isCommitted && !Object.is(refreshCell.token, token);
	if (!refreshCell.isCommitted || isRefreshing) addCommit(fiber, () => {
		refreshCell.token = token;
		refreshCell.isCommitted = true;
	});
	const previous = fiber.isRefreshing;
	fiber.isRefreshing = previous || isRefreshing;
	try {
		return fn();
	} finally {
		fiber.isRefreshing = previous;
	}
}
//#endregion
export { useRefreshScope };
