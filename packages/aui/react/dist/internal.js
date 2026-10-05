import { __exportAll } from "./_virtual/_rolldown/runtime.js";
import { useComposerInputPluginRegistryOptional } from "./primitives/composer/ComposerInputPluginContext.js";
import { useSmoothStatus, withSmoothContextProvider } from "./utils/smooth/SmoothContext.js";
import { useSmooth } from "./utils/smooth/useSmooth.js";
import { splitLocalRuntimeOptions } from "./legacy-runtime/runtime-cores/local/LocalRuntimeOptions.js";
import { AssistantRuntimeImpl, BaseAssistantRuntimeCore, CompositeContextProvider, DefaultThreadComposerRuntimeCore, MessageRepository, ThreadRuntimeImpl, getAutoStatus } from "@assistant-ui/core/internal";
//#region src/internal.ts
var internal_exports = /* @__PURE__ */ __exportAll({
	AssistantRuntimeImpl: () => AssistantRuntimeImpl,
	BaseAssistantRuntimeCore: () => BaseAssistantRuntimeCore,
	CompositeContextProvider: () => CompositeContextProvider,
	DefaultThreadComposerRuntimeCore: () => DefaultThreadComposerRuntimeCore,
	MessageRepository: () => MessageRepository,
	ThreadRuntimeImpl: () => ThreadRuntimeImpl,
	getAutoStatus: () => getAutoStatus,
	splitLocalRuntimeOptions: () => splitLocalRuntimeOptions,
	useComposerInputPluginRegistryOptional: () => useComposerInputPluginRegistryOptional,
	useSmooth: () => useSmooth,
	useSmoothStatus: () => useSmoothStatus,
	withSmoothContextProvider: () => withSmoothContextProvider
});
//#endregion
export { AssistantRuntimeImpl, BaseAssistantRuntimeCore, CompositeContextProvider, DefaultThreadComposerRuntimeCore, MessageRepository, ThreadRuntimeImpl, getAutoStatus, internal_exports, splitLocalRuntimeOptions, useComposerInputPluginRegistryOptional, useSmooth, useSmoothStatus, withSmoothContextProvider };
