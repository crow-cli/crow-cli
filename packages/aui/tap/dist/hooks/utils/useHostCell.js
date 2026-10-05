import { getCurrentResourceFiber } from "../../core/helpers/execution-context.js";
import { addCommit } from "../../core/helpers/root.js";
import { throwHookOrderChanged, throwRenderedMoreHooks } from "../../react-hooks/utils/hookErrors.js";
//#region src/hooks/utils/useHostCell.ts
const useHostCell = (target) => {
	const parent = getCurrentResourceFiber();
	const index = parent.currentIndex++;
	const existing = parent.cells[index];
	let cell;
	if (existing === void 0) {
		if (!parent.isFirstRender) throwRenderedMoreHooks();
		const isMap = target instanceof Map;
		cell = {
			type: "host",
			fiber: isMap ? null : target,
			fibers: isMap ? target : null
		};
		parent.cells[index] = cell;
		(parent.hostCells ??= []).push(cell);
	} else {
		if (existing.type !== "host") throwHookOrderChanged();
		cell = existing;
	}
	if (cell.fibers === null && cell.fiber !== target) addCommit(parent, () => {
		cell.fiber = target;
	});
	return cell;
};
//#endregion
export { useHostCell };
