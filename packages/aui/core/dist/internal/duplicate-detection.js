//#region src/internal/duplicate-detection.ts
const KEY = Symbol.for("@assistant-ui/core.loaded");
function checkDuplicateCore() {
	const g = globalThis;
	if (g[KEY]) console.warn("[@assistant-ui/core] Multiple copies of @assistant-ui/core are loaded into the same runtime. This causes subtle bugs (tools not reaching the runtime, context lookups returning the wrong provider, instanceof checks failing). Run `npx assistant-ui doctor` to diagnose.");
	g[KEY] = true;
}
//#endregion
export { checkDuplicateCore };
