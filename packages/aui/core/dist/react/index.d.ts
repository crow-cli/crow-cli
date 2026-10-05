/// <reference path="../store/scope-registration.d.ts" preserve="true" />
/// <reference path="types/store-augmentation.d.ts" preserve="true" />
export { makeAssistantTool, type AssistantTool, } from "./model-context/makeAssistantTool.js";
export { type AssistantToolUI, makeAssistantToolUI, } from "./model-context/makeAssistantToolUI.js";
export { type AssistantDataUI, makeAssistantDataUI, } from "./model-context/makeAssistantDataUI.js";
export { useAssistantInstructions } from "./model-context/useAssistantInstructions.js";
export { useAssistantContext, type AssistantContextConfig, } from "./model-context/useAssistantContext.js";
export { useAssistantTool, type AssistantToolProps, } from "./model-context/useAssistantTool.js";
export { useAssistantToolUI, type AssistantToolUIProps, } from "./model-context/useAssistantToolUI.js";
export { useAssistantDataUI, type AssistantDataUIProps, } from "./model-context/useAssistantDataUI.js";
export { useInlineRender } from "./model-context/useInlineRender.js";
export { type Toolkit, type ToolDefinition, type ToolkitDefinition, type ToolkitDefinitionEntry, type ToolCallText, } from "./model-context/toolbox.js";
export { defineToolkit } from "./model-context/define-toolkit.js";
export { stubTool } from "./model-context/stub-tool.js";
export { externalTool } from "./model-context/external-tool.js";
export { useAuiToolOverrides } from "./model-context/useAuiToolOverrides.js";
export { hitl, hitlTool, humanTool } from "./model-context/human-tool.js";
export { providerTool, type ProviderToolConfig, } from "./model-context/provider-tool.js";
export { defineMcpToolkit, type McpToolkitEntry, type McpToolkitDefinition, type McpToolkitToolConfig, } from "./model-context/define-mcp-toolkit.js";
/**
 * @deprecated Since 2026-06-14 — migrate to the Unstable / Experimental API.
 * Scheduled for removal on/after 2026-09-14. See
 * {@link https://www.assistant-ui.com/docs/tools/interactables#migrating-from-the-previous-api | Interactables migration guide}.
 */
export { useAssistantInteractable, type AssistantInteractableProps, } from "./interactables-legacy/useAssistantInteractable.js";
/**
 * @deprecated Since 2026-06-14 — migrate to the Unstable / Experimental API.
 * Scheduled for removal on/after 2026-09-14. See
 * {@link https://www.assistant-ui.com/docs/tools/interactables#migrating-from-the-previous-api | Interactables migration guide}.
 */
export { useInteractableState } from "./interactables-legacy/useInteractableState.js";
export { 
/** @deprecated Unstable / Experimental — may change in any release. */
unstable_useInteractable, type Unstable_InteractableConfig, type Unstable_InferInteractableState, type Unstable_InteractableVersionInfo, } from "./model-context/useInteractable.js";
export { 
/** @deprecated Unstable / Experimental — may change in any release. */
unstable_useInteractableState, } from "./model-context/useInteractableState.js";
export { 
/** @deprecated Unstable / Experimental — may change in any release. */
unstable_useInteractableVersions, } from "./model-context/useInteractableVersions.js";
export { 
/** @deprecated Unstable / Experimental — may change in any release. */
unstable_interactableTool, type Unstable_InteractableToolConfig, type Unstable_InteractableToolRenderProps, } from "./model-context/interactableTool.js";
export { useToolArgsStatus, type ToolArgsStatus, } from "./model-context/useToolArgsStatus.js";
export { Tools, type McpAppResourceOutput } from "./client/Tools.js";
export { DataRenderers } from "./client/DataRenderers.js";
/**
 * @deprecated Since 2026-06-14 — migrate to the Unstable / Experimental API.
 * Scheduled for removal on/after 2026-09-14. See
 * {@link https://www.assistant-ui.com/docs/tools/interactables#migrating-from-the-previous-api | Interactables migration guide}.
 */
export { Interactables } from "./interactables-legacy/Interactables.js";
export { 
/** @deprecated Unstable / Experimental — may change in any release. */
unstable_Interactables, } from "./client/Interactables.js";
export type { EmptyMessagePartComponent, EmptyMessagePartProps, TextMessagePartComponent, TextMessagePartProps, ReasoningMessagePartComponent, ReasoningMessagePartProps, SourceMessagePartComponent, SourceMessagePartProps, ImageMessagePartComponent, ImageMessagePartProps, FileMessagePartComponent, FileMessagePartProps, Unstable_AudioMessagePartComponent, Unstable_AudioMessagePartProps, DataMessagePartComponent, DataMessagePartProps, ToolCallMessagePartComponent, ToolCallMessagePartProps, ReasoningGroupProps, ReasoningGroupComponent, QuoteMessagePartComponent, QuoteMessagePartProps, GenerativeUIComponentRegistry, GenerativeUIMessagePartComponent, GenerativeUIMessagePartProps, GenerativeUIRenderProps, } from "./types/MessagePartComponentTypes.js";
export type { ToolsState, ToolsMethods, ToolsClientSchema, } from "./types/scopes/tools.js";
export type { DataRenderersState, DataRenderersMethods, DataRenderersClientSchema, } from "./types/scopes/dataRenderers.js";
export type { 
/** @deprecated Since 2026-06-14 — migrate to the Unstable / Experimental API. */
InteractableStateSchema, 
/** @deprecated Since 2026-06-14 — migrate to the Unstable / Experimental API. */
InteractablesState, 
/** @deprecated Since 2026-06-14 — migrate to the Unstable / Experimental API. */
InteractableDefinition, 
/** @deprecated Since 2026-06-14 — migrate to the Unstable / Experimental API. */
InteractableRegistration, 
/** @deprecated Since 2026-06-14 — migrate to the Unstable / Experimental API. */
InteractablesMethods, 
/** @deprecated Since 2026-06-14 — migrate to the Unstable / Experimental API. */
InteractablePersistedState, 
/** @deprecated Since 2026-06-14 — migrate to the Unstable / Experimental API. */
InteractablePersistenceAdapter, 
/** @deprecated Since 2026-06-14 — migrate to the Unstable / Experimental API. */
InteractablePersistenceStatus, 
/** @deprecated Since 2026-06-14 — migrate to the Unstable / Experimental API. */
InteractablesClientSchema, } from "./interactables-legacy/scopes.js";
export type { Unstable_InteractableStateSchema, Unstable_InteractablesState, Unstable_InteractableDefinition, Unstable_InteractableRegistration, Unstable_InteractablesMethods, Unstable_InteractablePersistedState, Unstable_InteractablePersistenceAdapter, Unstable_InteractablePersistenceStatus, Unstable_InteractablesClientSchema, Unstable_InteractablesConfig, } from "./types/scopes/interactables.js";
export { MessageAttachmentByIndexProvider, ComposerAttachmentByIndexProvider, } from "./providers/AttachmentByIndexProvider.js";
export { ThreadListItemRuntimeProvider } from "./providers/ThreadListItemRuntimeProvider.js";
export { MessageByIndexProvider } from "./providers/MessageByIndexProvider.js";
export { PartByIndexProvider } from "./providers/PartByIndexProvider.js";
export { TextMessagePartProvider } from "./providers/TextMessagePartProvider.js";
export { ChainOfThoughtByIndicesProvider } from "./providers/ChainOfThoughtByIndicesProvider.js";
export { ThreadListItemByIndexProvider } from "./providers/ThreadListItemByIndexProvider.js";
export { ChainOfThoughtPartByIndexProvider } from "./providers/ChainOfThoughtPartByIndexProvider.js";
export { SuggestionByIndexProvider, type SuggestionByIndexProviderProps, } from "./providers/SuggestionByIndexProvider.js";
export { QueueItemByIndexProvider, type QueueItemByIndexProviderProps, } from "./providers/QueueItemByIndexProvider.js";
export { ReadonlyThreadProvider } from "./providers/ReadonlyThreadProvider.js";
export { RuntimeAdapter } from "./RuntimeAdapter.js";
export { RuntimeAdapterProvider, useRuntimeAdapters, type RuntimeAdapters, } from "./runtimes/RuntimeAdapterProvider.js";
export { useExternalStoreRuntime } from "./runtimes/useExternalStoreRuntime.js";
export { useExternalStoreSharedOptions } from "./runtimes/useExternalStoreSharedOptions.js";
export { useExternalMessageConverter, convertExternalMessages, createExternalMessageConversionCache, } from "./runtimes/external-message-converter.js";
export type { ExternalMessageConversionCache, JoinStrategy, } from "./runtimes/external-message-converter.js";
export { createMessageConverter } from "./runtimes/createMessageConverter.js";
export { useStreamingTiming, type StreamingTimingAccessors, type StreamingTimingOptions, type StreamingTimingState, } from "./runtimes/useStreamingTiming.js";
export { createRuntimeExtras, unstable_createRuntimeExtrasFromBrand, type RuntimeExtras, } from "./runtimes/createRuntimeExtras.js";
export { RemoteThreadListHookInstanceManager } from "./runtimes/RemoteThreadListHookInstanceManager.js";
export { RemoteThreadListThreadListRuntimeCore } from "./runtimes/RemoteThreadListThreadListRuntimeCore.js";
export { useRemoteThreadListRuntime } from "./runtimes/useRemoteThreadListRuntime.js";
export { useCloudThreadListAdapter } from "./runtimes/cloud/useCloudThreadListAdapter.js";
export { createCloudThreadListAdapter, type CloudThreadListAdapterOptions, } from "./runtimes/cloud/createCloudThreadListAdapter.js";
export { useCloudThreadListRuntime } from "./runtimes/cloud/useCloudThreadListRuntime.js";
export { useAssistantTransportRuntime, useAssistantTransportSendCommand, useAssistantTransportState, } from "./runtimes/assistant-transport/useAssistantTransportRuntime.js";
export type { AssistantTransportConnectionMetadata, AssistantTransportCommand, AssistantTransportOptions, AssistantTransportProtocol, SendCommandsRequestBody, } from "./runtimes/assistant-transport/types.js";
export { useAssistantCloudThreadHistoryAdapter } from "./runtimes/cloud/AssistantCloudThreadHistoryAdapter.js";
export { CloudFileAttachmentAdapter } from "./runtimes/cloud/CloudFileAttachmentAdapter.js";
export { createLocalStorageAdapter, type AsyncStorageLike, } from "./adapters/LocalStorageThreadListAdapter.js";
export { createSimpleTitleAdapter, type TitleGenerationAdapter, } from "./adapters/TitleGenerationAdapter.js";
export { AssistantProviderBase, getRenderComponent, type AssistantProviderBaseProps, } from "./AssistantProvider.js";
export { ThreadPrimitiveMessages, ThreadPrimitiveMessagesImpl, ThreadPrimitiveMessageByIndex, ThreadPrimitiveUnstable_MessageById, } from "./primitives/thread/ThreadMessages.js";
export { MessagePrimitiveParts, MessagePartComponent, MessagePrimitivePartByIndex, defaultComponents as messagePartsDefaultComponents, type EnrichedPartState, type PartState, } from "./primitives/message/MessageParts.js";
export { MessagePrimitiveGroupedParts } from "./primitives/message/MessageGroupedParts.js";
export { groupPartByType, type GroupByContext } from "./utils/groupParts.js";
export { MessagePrimitiveGenerativeUI, GenerativeUIRender, GenerativeUIRenderError, } from "./primitives/generativeUI/GenerativeUI.js";
export { MessagePrimitiveQuote } from "./primitives/message/MessageQuote.js";
export { MessagePrimitiveAttachments, MessagePrimitiveAttachmentByIndex, } from "./primitives/message/MessageAttachments.js";
export { ComposerPrimitiveAttachments, ComposerPrimitiveAttachmentByIndex, } from "./primitives/composer/ComposerAttachments.js";
export { ComposerPrimitiveQueue } from "./primitives/composer/ComposerQueue.js";
export { ThreadListPrimitiveItems, ThreadListPrimitiveItemByIndex, } from "./primitives/threadList/ThreadListItems.js";
export { ChainOfThoughtPrimitiveParts } from "./primitives/chainOfThought/ChainOfThoughtParts.js";
export { PartPrimitiveMessages, PartPrimitiveMessagesImpl, } from "./primitives/part/PartMessages.js";
export { MessagePartPrimitiveInProgress } from "./primitives/messagePart/MessagePartInProgress.js";
export { ThreadListItemPrimitiveTitle } from "./primitives/threadListItem/ThreadListItemTitle.js";
export { ThreadPrimitiveSuggestions, ThreadPrimitiveSuggestionsImpl, ThreadPrimitiveSuggestionByIndex, } from "./primitives/thread/ThreadSuggestions.js";
export { ComposerPrimitiveIf, type UseComposerIfProps, } from "./primitives/composer/ComposerIf.js";
export { getMessageQuote } from "./utils/getMessageQuote.js";
export { useThreadMessages } from "./primitive-hooks/useThreadMessages.js";
export { unstable_useThreadMessageIds } from "./primitive-hooks/useThreadMessageIds.js";
export { useThreadIsRunning } from "./primitive-hooks/useThreadIsRunning.js";
export { useThreadIsEmpty } from "./primitive-hooks/useThreadIsEmpty.js";
export { useComposerSend } from "./primitive-hooks/useComposerSend.js";
export { useComposerCancel } from "./primitive-hooks/useComposerCancel.js";
export { useComposerDictate } from "./primitive-hooks/useComposerDictate.js";
export { useComposerAddAttachment } from "./primitive-hooks/useComposerAddAttachment.js";
export { useMessageReload } from "./primitive-hooks/useMessageReload.js";
export { useMessageBranching } from "./primitive-hooks/useMessageBranching.js";
export { useActionBarCopy, type UseActionBarCopyOptions, } from "./primitive-hooks/useActionBarCopy.js";
export { useActionBarEdit } from "./primitive-hooks/useActionBarEdit.js";
export { useActionBarReload } from "./primitive-hooks/useActionBarReload.js";
export { useActionBarFeedbackPositive, useActionBarFeedbackNegative, } from "./primitive-hooks/useActionBarFeedback.js";
export { useActionBarSpeak } from "./primitive-hooks/useActionBarSpeak.js";
export { useActionBarStopSpeaking } from "./primitive-hooks/useActionBarStopSpeaking.js";
export { useVoiceState, useVoiceVolume, useVoiceControls, } from "./primitive-hooks/useVoice.js";
export { useBranchPickerNext } from "./primitive-hooks/useBranchPickerNext.js";
export { useBranchPickerPrevious } from "./primitive-hooks/useBranchPickerPrevious.js";
export { useSuggestionTrigger, type UseSuggestionTriggerOptions, } from "./primitive-hooks/useSuggestionTrigger.js";
export { useThreadListItemArchive } from "./primitive-hooks/useThreadListItemArchive.js";
export { useThreadListItemDelete } from "./primitive-hooks/useThreadListItemDelete.js";
export { useThreadListItemUnarchive } from "./primitive-hooks/useThreadListItemUnarchive.js";
export { useThreadListItemTrigger } from "./primitive-hooks/useThreadListItemTrigger.js";
export { useThreadListNew } from "./primitive-hooks/useThreadListNew.js";
export { useThreadListLoadMore } from "./primitive-hooks/useThreadListLoadMore.js";
export { useEditComposerCancel } from "./primitive-hooks/useEditComposerCancel.js";
export { useEditComposerSend } from "./primitive-hooks/useEditComposerSend.js";
export { useMessageError } from "./primitive-hooks/useMessageError.js";
export { AssistantRuntimeProvider } from "./AssistantRuntimeProvider.js";
export { useLocalRuntime, splitLocalRuntimeOptions, type LocalRuntimeOptions, } from "./runtimes/useLocalRuntime.js";