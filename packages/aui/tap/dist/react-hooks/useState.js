import { useReducerImpl } from "./useReducer.js";
//#region src/react-hooks/useState.ts
const stateReducer = (state, action) => typeof action === "function" ? action(state) : action;
const stateInit = (initial) => initial === void 0 ? void 0 : typeof initial === "function" ? initial() : initial;
function useState(initial) {
	return useReducerImpl(stateReducer, initial, stateInit, true);
}
//#endregion
export { useState };
