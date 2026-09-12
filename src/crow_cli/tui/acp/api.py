# mypy: disable-error-code="empty-body"
"""
ACP remote API
"""

from crow_cli.tui import jsonrpc
from crow_cli.tui.acp import protocol

API = jsonrpc.API()


@API.method()
def initialize(
    protocolVersion: int,
    clientCapabilities: protocol.ClientCapabilities,
    clientInfo: protocol.Implementation,
) -> protocol.InitializeResponse:
    """https://agentclientprotocol.com/protocol/initialization"""
    ...


@API.method(name="session/new")
def session_new(
    cwd: str, mcpServers: list[protocol.McpServer]
) -> protocol.NewSessionResponse:
    """https://agentclientprotocol.com/protocol/session-setup#session-id"""
    ...


@API.method(name="session/load")
def session_load(
    cwd: str, mcpServers: list[protocol.McpServer], sessionId: str
) -> protocol.LoadSessionResponse:
    """https://agentclientprotocol.com/protocol/session-setup#loading-a-session"""
    ...


@API.notification(name="session/cancel")
def session_cancel(sessionId: str, _meta: dict):
    """https://agentclientprotocol.com/protocol/prompt-turn#cancellation"""
    ...


@API.method(name="session/prompt")
def session_prompt(
    prompt: list[protocol.ContentBlock], sessionId: str
) -> protocol.SessionPromptResponse:
    """https://agentclientprotocol.com/protocol/prompt-turn#1-user-message"""
    ...


@API.method(name="session/set_mode")
def session_set_mode(sessionId: str, modeId: str) -> protocol.SetSessionModeResponse:
    """https://agentclientprotocol.com/protocol/session-modes#from-the-client"""
    ...


@API.method(name="session/set_config_option")
def session_set_config_option(
    sessionId: str, configId: str, value: str | bool
) -> protocol.SetSessionConfigOptionResponse:
    """https://agentclientprotocol.com/protocol/v1/session-config-options#setting-a-config-option

    Valid while the agent is idle OR generating. For a `select` option the
    value must be one of the option's listed values; the reply carries the
    complete config state.
    """
    ...


@API.method(name="session/list")
def session_list(
    cwd: str | None = None, cursor: str | None = None
) -> protocol.ListSessionsResponse:
    """https://agentclientprotocol.com/protocol/v1/session-list"""
    ...
