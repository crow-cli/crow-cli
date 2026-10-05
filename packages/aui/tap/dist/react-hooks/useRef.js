import { getCurrentResourceFiber } from "../core/helpers/execution-context.js";
import { throwHookOrderChanged, throwRenderedMoreHooks } from "./utils/hookErrors.js";
//#region src/react-hooks/useRef.ts
function useRef(initialValue) {
	const fiber = getCurrentResourceFiber();
	const index = fiber.currentIndex++;
	const cell = fiber.cells[index];
	if (cell === void 0) {
		if (!fiber.isFirstRender) throwRenderedMoreHooks();
		const ref = { current: initialValue };
		fiber.cells[index] = {
			type: "ref",
			ref
		};
		return ref;
	}
	if (cell.type !== "ref") return throwHookOrderChanged();
	return cell.ref;
}
//#endregion
export { useRef };
