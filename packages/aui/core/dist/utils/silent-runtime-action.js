//#region src/utils/silent-runtime-action.ts
const SILENT_RUNTIME_ACTION = Symbol.for("assistant-ui.silent-runtime-action");
const isSilentRuntimeAction = (error) => typeof error === "object" && error !== null && SILENT_RUNTIME_ACTION in error;
//#endregion
export { SILENT_RUNTIME_ACTION, isSilentRuntimeAction };
