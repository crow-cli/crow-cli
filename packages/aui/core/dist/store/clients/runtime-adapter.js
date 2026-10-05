import { ModelContext } from "./model-context-client.js";
import { Derived } from "@assistant-ui/store/client";
//#region src/store/clients/runtime-adapter.ts
const baseRuntimeAdapterTransformScopes = (scopes, parent) => {
	scopes.thread ??= Derived({
		source: "threads",
		query: { type: "main" },
		get: (aui) => aui.threads.thread("main")
	});
	scopes.threadListItem ??= Derived({
		source: "threads",
		query: { type: "main" },
		get: (aui) => aui.threads.item("main")
	});
	scopes.composer ??= Derived({
		source: "thread",
		query: {},
		get: (aui) => aui.threads.thread("main").composer()
	});
	if (!scopes.modelContext && parent.modelContext.source === null) scopes.modelContext = ModelContext();
	if (!scopes.suggestions && parent.suggestions.source === null) scopes.suggestions = Derived({
		source: "thread",
		query: {},
		get: (aui) => aui.thread.suggestions()
	});
};
//#endregion
export { baseRuntimeAdapterTransformScopes };
