//#region src/runtime/utils/thread-runtime-lifecycle.ts
const generations = /* @__PURE__ */ new WeakMap();
const captureThreadRuntimeGeneration = (runtime) => {
	let generation = generations.get(runtime);
	if (!generation) {
		generation = new AbortController();
		generations.set(runtime, generation);
	}
	return generation.signal;
};
const disposals = /* @__PURE__ */ new WeakMap();
const disposalOf = (runtime) => {
	let disposal = disposals.get(runtime);
	if (!disposal) {
		disposal = new AbortController();
		disposals.set(runtime, disposal);
	}
	return disposal;
};
/** Aborts only when the runtime is disposed for good, never on invalidation. */
const captureThreadRuntimeDisposal = (runtime) => disposalOf(runtime).signal;
const invalidateThreadRuntime = (runtime) => {
	const generation = generations.get(runtime);
	if (generation?.signal.aborted) return;
	generations.delete(runtime);
	generation?.abort();
};
const endVoiceSession = (runtime) => {
	if (!runtime.voice) return;
	try {
		runtime.disconnectVoice();
	} catch (error) {
		console.error("[assistant-ui] Voice cleanup threw while discarding a thread runtime", error);
	}
};
const supersedeThreadRuntime = (runtime) => {
	endVoiceSession(runtime);
	invalidateThreadRuntime(runtime);
};
const disposeThreadRuntime = (runtime) => {
	const generation = generations.get(runtime) ?? new AbortController();
	generations.set(runtime, generation);
	generation.abort();
	disposalOf(runtime).abort();
	endVoiceSession(runtime);
};
//#endregion
export { captureThreadRuntimeDisposal, captureThreadRuntimeGeneration, disposeThreadRuntime, invalidateThreadRuntime, supersedeThreadRuntime };
