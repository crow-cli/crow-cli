//#region src/utils/derived-hook.ts
const DERIVED_HOOK = Symbol("assistant-ui.derived-hook");
const markDerivedHook = (hook) => {
	hook[DERIVED_HOOK] = true;
};
const isDerivedHook = (hook) => hook[DERIVED_HOOK] === true;
//#endregion
export { isDerivedHook, markDerivedHook };
