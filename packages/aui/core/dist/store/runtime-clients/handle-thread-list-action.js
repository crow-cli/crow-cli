import { handleRuntimeAction } from "./handle-runtime-action.js";
//#region src/store/runtime-clients/handle-thread-list-action.ts
const handleThreadListAction = (action, execute) => handleRuntimeAction(`thread list ${action}`, execute);
//#endregion
export { handleThreadListAction };
