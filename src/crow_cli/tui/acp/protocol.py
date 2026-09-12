from typing_extensions import Any, TypedDict, Required, Literal


class SchemaDict(TypedDict, total=False, extra_items=Any):
    pass


# ---------------------------------------------------------------------------------------
# Types


# https://agentclientprotocol.com/rfds/session-usage#context-window-and-cost-via-session/update
class Cost(TypedDict, total=False, extra_items=Any):
    amount: float
    currency: str


class FileSystemCapability(SchemaDict, total=False, extra_items=Any):
    readTextFile: bool
    writeTextFile: bool


# https://agentclientprotocol.com/protocol/schema#clientcapabilities
class ClientCapabilities(SchemaDict, total=False, extra_items=Any):
    fs: FileSystemCapability
    terminal: bool


# https://agentclientprotocol.com/protocol/schema#implementation
class Implementation(SchemaDict, total=False, extra_items=Any):
    name: Required[str]
    title: str | None
    version: Required[str]


# https://agentclientprotocol.com/protocol/schema#promptcapabilities
class PromptCapabilities(SchemaDict, total=False, extra_items=Any):
    audio: bool
    embeddedContent: bool
    image: bool


# https://agentclientprotocol.com/protocol/v1/session-list
class SessionListCapabilities(SchemaDict, total=False, extra_items=Any):
    additionalDirectories: bool
    delete: bool


class SessionCapabilities(SchemaDict, total=False, extra_items=Any):
    list: SessionListCapabilities


class SessionInfo(SchemaDict, total=False, extra_items=Any):
    sessionId: Required[str]
    cwd: Required[str]
    additionalDirectories: list[str]
    title: str
    updatedAt: str
    _meta: dict


class ListSessionsResponse(SchemaDict, total=False, extra_items=Any):
    sessions: Required[list[SessionInfo]]
    nextCursor: str


# https://agentclientprotocol.com/protocol/schema#agentcapabilities
class AgentCapabilities(SchemaDict, total=False, extra_items=Any):
    loadSession: bool
    promptCapabilities: PromptCapabilities
    sessionCapabilities: SessionCapabilities


class AuthMethod(SchemaDict, total=False, extra_items=Any):
    description: str | None
    id: Required[str]
    name: Required[str]


# https://agentclientprotocol.com/protocol/schema#envvariable
class EnvVariable(SchemaDict, total=False, extra_items=Any):
    _meta: dict
    name: Required[str]
    value: Required[str]


# https://agentclientprotocol.com/protocol/schema#terminalexitstatus
class TerminalExitStatus(SchemaDict, total=False, extra_items=Any):
    _meta: dict
    exitCode: int | None
    signal: str | None


# https://agentclientprotocol.com/protocol/schema#httpheader
class HttpHeader(SchemaDict, total=False, extra_items=Any):
    name: Required[str]
    value: Required[str]


# https://agentclientprotocol.com/protocol/schema#mcpserver
# Stdio servers carry command/args/env; http/sse servers carry url (+headers).
class McpServer(SchemaDict, total=False, extra_items=Any):
    args: list[str]
    command: str
    env: list[EnvVariable]
    name: str
    url: str
    headers: list[HttpHeader]
    type: str


# https://modelcontextprotocol.io/specification/2025-06-18/server/resources#annotations
class Annotations(SchemaDict, total=False, extra_items=Any):
    audience: list[str]
    priority: float
    lastModified: str


class TextContent(SchemaDict, total=False, extra_items=Any):
    type: Required[str]
    text: Required[str]
    annotations: Annotations


class ImageContent(SchemaDict, total=False, extra_items=Any):
    type: Required[str]
    data: Required[str]
    mimeType: Required[str]
    url: str
    annotations: Annotations


class AudioContent(SchemaDict, total=False, extra_items=Any):
    type: Required[str]
    data: Required[str]
    mimeType: Required[str]
    Annotations: Annotations


class EmbeddedResourceText(SchemaDict, total=False, extra_items=Any):
    uri: Required[str]
    text: Required[str]
    mimeType: str


class EmbeddedResourceBlob(SchemaDict, total=False, extra_items=Any):
    uri: Required[str]
    blob: Required[str]
    mimeType: str


# https://agentclientprotocol.com/protocol/content#embedded-resource
class EmbeddedResourceContent(SchemaDict, total=False, extra_items=Any):
    type: Required[str]
    resource: EmbeddedResourceText | EmbeddedResourceBlob


class ResourceLinkContent(SchemaDict, total=False, extra_items=Any):
    annotations: Annotations | None
    description: str | None
    mimeType: str | None
    name: Required[str]
    size: int | None
    title: str | None
    type: Required[str]
    uri: Required[str]


# https://agentclientprotocol.com/protocol/schema#contentblock
type ContentBlock = (
    TextContent
    | ImageContent
    | AudioContent
    | EmbeddedResourceContent
    | ResourceLinkContent
)


# https://agentclientprotocol.com/protocol/schema#param-user-message-chunk
class UserMessageChunk(SchemaDict, total=False, extra_items=Any):
    content: Required[ContentBlock]
    sessionUpdate: Required[Literal["user_message_chunk"]]


class AgentMessageChunk(SchemaDict, total=False, extra_items=Any):
    content: Required[ContentBlock]
    sessionUpdate: Required[Literal["agent_message_chunk"]]


class AgentThoughtChunk(SchemaDict, total=False, extra_items=Any):
    content: Required[ContentBlock]
    sessionUpdate: Required[Literal["agent_thought_chunk"]]


class ToolCallContentContent(SchemaDict, total=False, extra_items=Any):
    content: Required[ContentBlock]
    type: Required[Literal["content"]]


# https://agentclientprotocol.com/protocol/schema#param-diff
class ToolCallContentDiff(SchemaDict, total=False, extra_items=Any):
    newText: Required[str]
    oldText: str | None
    path: Required[str]
    type: Required[Literal["diff"]]


class ToolCallContentTerminal(SchemaDict, total=False, extra_items=Any):
    terminalId: Required[str]
    type: Required[Literal["terminal"]]


# https://agentclientprotocol.com/protocol/schema#toolcallcontent
type ToolCallContent = (
    ToolCallContentContent | ToolCallContentDiff | ToolCallContentTerminal
)

# https://agentclientprotocol.com/protocol/schema#toolkind
type ToolKind = Literal[
    "read",
    "edit",
    "delete",
    "move",
    "search",
    "execute",
    "think",
    "fetch",
    "switch_mode",
    "other",
]

type ToolCallStatus = Literal["pending", "in_progress", "completed", "failed"]


class ToolCallLocation(SchemaDict, total=False, extra_items=Any):
    line: int | None
    path: Required[str]


type ToolCallId = str


# https://agentclientprotocol.com/protocol/schema#toolcall
class ToolCall(SchemaDict, total=False, extra_items=Any):
    _meta: dict
    content: list[ToolCallContent]
    kind: ToolKind
    locations: list[ToolCallLocation]
    rawInput: dict
    rawOutput: dict
    sessionUpdate: Required[Literal["tool_call"]]
    status: ToolCallStatus
    title: Required[str]
    toolCallId: Required[ToolCallId]


# https://agentclientprotocol.com/protocol/schema#toolcallupdate
class ToolCallUpdate(SchemaDict, total=False, extra_items=Any):
    _meta: dict
    content: list[ToolCallContent] | None
    kind: ToolKind | None
    locations: list | None
    rawInput: dict
    rawOutput: dict
    sessionUpdate: Required[Literal["tool_call_update"]]
    status: ToolCallStatus | None
    title: str | None
    toolCallId: Required[ToolCallId]


# https://agentclientprotocol.com/protocol/schema#param-tool-call
# Use in the session/request_permission call (not the same as ToolCallUpdate)
class ToolCallUpdatePermissionRequest(SchemaDict, total=False, extra_items=Any):
    _meta: dict
    content: list[ToolCallContent] | None
    kind: ToolKind | None
    locations: list | None
    rawInput: dict
    rawOutput: dict
    status: ToolCallStatus | None
    title: str | None
    toolCallId: Required[ToolCallId]


class PlanEntry(SchemaDict, total=False, extra_items=Any):
    content: Required[str]
    priority: Literal["high", "medium", "low"]
    status: Literal["pending", "in_progress", "completed"]


type SessionModeId = str


# https://agentclientprotocol.com/protocol/schema#sessionmode
class SessionMode(SchemaDict, total=False, extra_items=Any):
    _meta: dict
    description: str | None
    id: Required[SessionModeId]
    name: Required[str]


class SessionModeState(SchemaDict, total=False, extra_items=Any):
    _meta: dict
    availableModes: Required[list[SessionMode]]
    currentModeId: Required[SessionModeId]


type ModelId = str


# https://agentclientprotocol.com/protocol/schema#modelinfo
class ModelInfo(SchemaDict, total=False, extra_items=Any):
    _meta: dict
    description: str | None
    modelId: Required[ModelId]
    name: Required[str]


# https://agentclientprotocol.com/protocol/schema#sessionmodelstate
class SessionModelState(SchemaDict, total=False, extra_items=Any):
    _meta: dict
    availableModels: Required[list[ModelInfo]]
    currentModelId: Required[ModelId]


# https://agentclientprotocol.com/protocol/v1/session-config-options
# Categories are UX hints only — a client MUST handle missing or unknown ones.
# Names beginning with "_" are free for custom use; the rest are reserved.
type ConfigOptionCategory = str
type ConfigOptionType = Literal["select", "boolean"]


class ConfigOptionValue(SchemaDict, total=False, extra_items=Any):
    _meta: dict
    description: str | None
    name: Required[str]
    value: Required[str]


class ConfigOption(SchemaDict, total=False, extra_items=Any):
    """One session-level selector the agent offers (model, mode, reasoning…).

    ``options`` is required for ``select`` and omitted for ``boolean``;
    ``currentValue`` is a string value id for the former, a bool for the
    latter. The agent MUST always supply a default, so a client that ignores
    an option it does not understand leaves the agent usable.
    """

    _meta: dict
    category: ConfigOptionCategory | None
    currentValue: Required[str | bool]
    description: str | None
    id: Required[str]
    name: Required[str]
    options: list[ConfigOptionValue]
    type: Required[ConfigOptionType]


# https://agentclientprotocol.com/protocol/schema#param-plan
class Plan(SchemaDict, total=False, extra_items=Any):
    entries: Required[list[PlanEntry]]
    sessionUpdate: Required[Literal["plan"]]


class AvailableCommandInput(SchemaDict, total=False, extra_items=Any):
    hint: Required[str]


class AvailableCommand(SchemaDict, total=False, extra_items=Any):
    description: Required[str]
    input: AvailableCommandInput | None
    name: Required[str]


class AvailableCommandsUpdate(SchemaDict, total=False, extra_items=Any):
    availableCommands: Required[list[AvailableCommand]]
    sessionUpdate: Required[Literal["available_commands_update"]]


class CurrentModeUpdate(SchemaDict, total=False, extra_items=Any):
    currentModeId: Required[str]
    sessionUpdate: Required[Literal["current_mode_update"]]


class ConfigOptionUpdate(SchemaDict, total=False, extra_items=Any):
    """Agent-initiated config change — always the COMPLETE option list.

    Sent when the agent changes something itself, e.g. falling back to another
    model on a rate limit, so the client's selectors never drift from truth.
    """

    configOptions: Required[list[ConfigOption]]
    sessionUpdate: Required[Literal["config_option_update"]]


class UsageUpdate(SchemaDict, total=False, extra_items=object):
    sessionUpdate: Required[Literal["usage_update"]]
    used: Required[int]
    size: Required[int]
    cost: Cost


type SessionUpdate = (
    UserMessageChunk
    | AgentMessageChunk
    | AgentThoughtChunk
    | ToolCall
    | ToolCallUpdate
    | Plan
    | AvailableCommandsUpdate
    | CurrentModeUpdate
    | ConfigOptionUpdate
    | UsageUpdate
)


class SessionNotification(TypedDict, total=False, extra_items=Any):
    sessionId: str
    update: SessionUpdate


type PermissionOptionKind = Literal[
    "allow_once", "allow_always", "reject_once", "reject_always"
]
type PermissionOptionId = str


class PermissionOption(TypedDict, total=False, extra_items=Any):
    _meta: dict
    kind: Required[PermissionOptionKind]
    name: Required[str]
    optionId: Required[PermissionOptionId]


class OutcomeCancelled(TypedDict, total=False, extra_items=Any):
    outcome: Literal["cancelled"]


class OutcomeSelected(TypedDict, total=False, extra_items=Any):
    optionId: Required[PermissionOptionId]
    outcome: Literal["selected"]


# https://agentclientprotocol.com/protocol/schema#requestpermissionoutcome
type RequestPermissionOutcome = OutcomeSelected | OutcomeCancelled

# ---------------------------------------------------------------------------------------
# RPC responses


class InitializeResponse(SchemaDict, total=False, extra_items=Any):
    agentCapabilities: AgentCapabilities
    authMethods: list[AuthMethod]
    protocolVersion: Required[int]


# https://agentclientprotocol.com/protocol/schema#newsessionresponse
class NewSessionResponse(SchemaDict, total=False, extra_items=Any):
    _meta: object
    sessionId: Required[str]
    # Array order is the agent's preferred priority; clients SHOULD respect it.
    configOptions: list[ConfigOption] | None
    # Unstable from here
    models: SessionModelState | None
    modes: SessionModeState | None


# https://agentclientprotocol.com/protocol/schema#loadsessionresponse
class LoadSessionResponse(SchemaDict, total=False, extra_items=Any):
    _meta: object
    configOptions: list[ConfigOption] | None
    modes: SessionModeState | None


class SessionPromptResponse(SchemaDict, total=False, extra_items=object):
    sessionId: Required[str]
    stopReason: Required[
        Literal[
            "end_turn",
            "max_tokens",
            "max_turn_requests",
            "refusal",
            "cancelled",
        ]
    ]
    usage: Usage


# https://agentclientprotocol.com/protocol/schema#requestpermissionresponse
class RequestPermissionResponse(TypedDict, total=False, extra_items=Any):
    _meta: dict
    outcome: Required[RequestPermissionOutcome]


# https://agentclientprotocol.com/protocol/schema#createterminalresponse
class CreateTerminalResponse(TypedDict, total=False, extra_items=Any):
    _meta: dict
    terminalId: Required[str]


# https://agentclientprotocol.com/protocol/schema#killterminalcommandresponse
class KillTerminalCommandResponse(TypedDict, total=False, extra_items=Any):
    _meta: dict


# https://agentclientprotocol.com/protocol/schema#terminaloutputresponse
class TerminalOutputResponse(TypedDict, total=False, extra_items=Any):
    _meta: dict
    exitStatus: TerminalExitStatus | None
    output: Required[str]
    truncated: Required[bool]


# https://agentclientprotocol.com/protocol/schema#releaseterminalresponse
class ReleaseTerminalResponse(TypedDict, total=False, extra_items=Any):
    _meta: dict


# https://agentclientprotocol.com/protocol/schema#waitforterminalexitresponse
class WaitForTerminalExitResponse(TypedDict, total=False, extra_items=Any):
    _meta: dict
    exitCode: int | None
    signal: str | None


# https://agentclientprotocol.com/protocol/schema#setsessionmoderesponse
class SetSessionModeResponse(TypedDict, total=False, extra_items=Any):
    meta: dict


# https://agentclientprotocol.com/protocol/v1/session-config-options#setting-a-config-option
class SetSessionConfigOptionResponse(SchemaDict, total=False, extra_items=Any):
    """Always the COMPLETE config state, so dependent changes come back too."""

    configOptions: Required[list[ConfigOption]]


# ---------------------------------------------------------------------------------------


# https://agentclientprotocol.com/rfds/session-usage#usage-fields
class Usage(TypedDict, total=False, extra_items=Any):
    total_tokens: Required[int]
    input_tokens: Required[int]
    output_tokens: Required[int]
    thought_tokens: int
    cached_read_tokens: int
    cached_write_tokens: int


# ---------------------------------------------------------------------------------------
# Config-option helpers — pure functions over the wire types above, so both the
# agent connection and the widgets can share them without an import cycle.


def find_config_option(
    options: list[ConfigOption],
    *,
    category: str | None = None,
    option_id: str | None = None,
) -> ConfigOption | None:
    """Find an option by semantic category, falling back to its id.

    Categories are UX hints that MUST NOT be required for correctness and may
    be absent or unrecognised, so the well-known id is the fallback rather than
    the other way round. Ties within a category resolve by array order, which
    is the agent's stated priority.
    """
    if category is not None:
        for option in options:
            if option.get("category") == category:
                return option
    if option_id is not None:
        for option in options:
            if option.get("id") == option_id:
                return option
    return None


def match_config_value(option: ConfigOption, wanted: str) -> str | None:
    """Resolve a user-supplied name to one of a select option's values.

    `-m qwen3.8-max-preview` is a config.yaml model NAME, which the agent
    publishes as an option's `name`; the value it wants back is the option's
    `value` (`provider:model_id` for crow's own agent). Accept either, exact
    match only — a near miss should surface the valid names, not guess.
    """
    for candidate in option.get("options") or []:
        if wanted in (candidate.get("value"), candidate.get("name")):
            return candidate["value"]
    return None


def config_value_names(option: ConfigOption) -> list[str]:
    """The display names of a select option's values, for error messages."""
    return [c["name"] for c in (option.get("options") or []) if "name" in c]


def config_current_name(option: ConfigOption) -> str | None:
    """Display name of an option's current value, or None if it has none."""
    current = option.get("currentValue")
    for candidate in option.get("options") or []:
        if candidate.get("value") == current:
            return candidate.get("name")
    return current if isinstance(current, str) else None
