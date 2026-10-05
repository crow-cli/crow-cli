//#region src/react-hooks/utils/hookErrors.ts
const throwRenderedMoreHooks = () => {
	throw new Error("Rendered more hooks than during the previous render. Hooks must be called in the exact same order in every render.");
};
const throwHookOrderChanged = () => {
	throw new Error("Hook order changed between renders");
};
//#endregion
export { throwHookOrderChanged, throwRenderedMoreHooks };
