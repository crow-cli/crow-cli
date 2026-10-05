//#region src/core/utils/stream/controller-guards.ts
const isClosedControllerError = (error) => error instanceof TypeError;
const enqueueIfOpen = (controller, chunk, onDrop) => {
	try {
		controller.enqueue(chunk);
	} catch (error) {
		if (!isClosedControllerError(error)) throw error;
		onDrop?.(error);
	}
};
const closeIfOpen = (controller) => {
	try {
		controller.close();
	} catch (error) {
		if (!isClosedControllerError(error)) throw error;
	}
};
//#endregion
export { closeIfOpen, enqueueIfOpen };
