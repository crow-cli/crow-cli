export { useAcpRuntime } from "./useAcpRuntime";
export type { UseAcpRuntimeOptions } from "./useAcpRuntime";

export {
  useAcpAgentCapabilities,
  useAcpAgentInfo,
  useAcpAvailableCommands,
  useAcpConfigOptions,
  useAcpConnectionState,
  useAcpCurrentModeId,
  useAcpPlan,
  useAcpSessionId,
  useAcpSessionTitle,
  useAcpSetConfigOption,
  useAcpUsage,
} from "./hooks";

export { acpExtras } from "./acpExtras";

export {
  AcpClient,
  AcpError,
  autoAllowPermissionHandler,
  cancelPermissionHandler,
} from "./AcpClient";
export { AcpClientV2 } from "./AcpClientV2";
export type {
  AcpClientLike,
  AcpClientOptions,
  AcpConnectionListener,
  AcpPermissionHandler,
  AcpSessionUpdateListener,
  AcpWebSocketFactory,
  AcpWebSocketLike,
} from "./AcpClient";

// Lower-level building blocks, deliberately public as advanced API.
export { AcpThreadController } from "./AcpThreadController";
export type {
  AcpPermissionsMode,
  AcpThreadControllerLike,
  AcpThreadControllerOptions,
} from "./AcpThreadController";
export {
  createAcpThreadState,
  isAcpStateRunning,
  reduceAcpThreadState,
  EMPTY_ACP_THREAD_STATE,
} from "./acpThreadState";
export type {
  AcpAssistantMessage,
  AcpLoadState,
  AcpPendingPermission,
  AcpRunState,
  AcpThreadEvent,
  AcpThreadMessage,
  AcpThreadState,
  AcpUserMessage,
} from "./acpThreadState";
export {
  projectAcpThreadRepository,
  toThreadMessage,
  toThreadMessageLike,
} from "./acpMessageProjection";

// Context compaction: the entity the reducer retains and the `data` part name
// a host registers a renderer under to draw it.
export {
  ACP_COMPACTION_PART,
  appendCompactionSummary,
  applyCompactionPatch,
  compactionSummaryText,
  isCompactionOpen,
  isCompactionPart,
  newCompactionPart,
  settleOpenCompactions,
} from "./compaction";
export type { AcpCompactionPart, AcpCompactionPatch } from "./compaction";
export { useAcpControllerState } from "./useAcpControllerState";

// Protocol types
export type {
  AcpAgentCapabilities,
  AcpAnnotations,
  AcpAudioContentBlock,
  AcpAuthMethod,
  AcpAvailableCommand,
  AcpBlobResourceContents,
  AcpClientCapabilities,
  AcpCompaction,
  AcpCompactionStatus,
  AcpConnectionState,
  AcpContentBlock,
  AcpCost,
  AcpEmbeddedResourceContentBlock,
  AcpEnvVariable,
  AcpExtras,
  AcpHttpHeader,
  AcpImageContentBlock,
  AcpImplementation,
  AcpInitializeResponse,
  AcpMcpCapabilities,
  AcpMcpServer,
  AcpPermissionOption,
  AcpPermissionOptionKind,
  AcpPermissionOutcome,
  AcpPermissionRequest,
  AcpPlanEntry,
  AcpPlanEntryPriority,
  AcpPlanEntryStatus,
  AcpPromptCapabilities,
  AcpResourceContents,
  AcpResourceLinkContentBlock,
  AcpSessionCapabilities,
  AcpSessionCapabilityFlag,
  AcpSessionConfigBoolean,
  AcpSessionConfigOption,
  AcpSessionConfigSelect,
  AcpSessionConfigSelectOption,
  AcpSessionInfo,
  AcpSessionListResult,
  AcpSessionMode,
  AcpSessionModeId,
  AcpSessionModeState,
  AcpSessionUpdate,
  AcpStopReason,
  AcpTextContentBlock,
  AcpTextResourceContents,
  AcpToolCall,
  AcpToolCallContent,
  AcpToolCallLocation,
  AcpToolCallStatus,
  AcpToolCallUpdate,
  AcpToolKind,
  AcpUsage,
} from "./types";
export { ACP_PROTOCOL_VERSION } from "./types";

// Conversion utilities (for advanced usage)
export {
  appendContentBlock,
  applySessionUpdateToContent,
  applyToolCallUpdate,
  attachToolCallApproval,
  buildToolCallPart,
  filterPromptBlocks,
  isAllowKind,
  isRejectKind,
  mergeToolCallPart,
  permissionOptionToApprovalOption,
  resolvePermissionOutcome,
  resolveToolCallApproval,
  stopReasonToMessageStatus,
  threadContentToAcpBlocks,
  toolCallContentToText,
} from "./conversions";
export type {
  AcpApprovalDecision,
  AcpPromptBlocks,
  AcpToolCallMetadata,
} from "./conversions";
