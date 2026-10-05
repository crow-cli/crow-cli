//#region src/core/helpers/execution-context.ts
let currentResourceFiber = null;
function withResourceFiber(fiber, fn) {
	fiber.currentIndex = 0;
	fiber.wipContextDeps = null;
	fiber.wipCommitCallbacks = [];
	const previousContext = currentResourceFiber;
	currentResourceFiber = fiber;
	try {
		fn();
		fiber.isFirstRender = false;
		if (fiber.cells.length !== fiber.currentIndex) throw new Error(`Rendered ${fiber.currentIndex} hooks but expected ${fiber.cells.length}. Hooks must be called in the exact same order in every render.`);
	} finally {
		currentResourceFiber = previousContext;
	}
}
function getCurrentResourceFiber() {
	if (!currentResourceFiber) throw new Error("No resource fiber available");
	return currentResourceFiber;
}
function peekResourceFiber() {
	return currentResourceFiber;
}
//#endregion
export { getCurrentResourceFiber, peekResourceFiber, withResourceFiber };
