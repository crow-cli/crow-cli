"""_parse_mcp_servers — the guard against the SDK's silent drop.

The SDK's NewSessionRequest.model_validate silently DROPS mcpServers list
items that fail validation (observed: a stdio dict missing the required
env list vanished, child came up toolless, no error anywhere). The driver
parses item-by-item BEFORE sending so bad shapes are loud, and fills the
two required-but-emptyable stdio fields.
"""

import pytest

from crow_cli.client.subagent import _parse_mcp_servers
from acp.schema import HttpMcpServer, McpServerStdio, SseMcpServer


def test_stdio_dict_becomes_model_with_filled_defaults():
    [s] = _parse_mcp_servers([{"name": "crow-mcp", "command": "uv"}])
    assert isinstance(s, McpServerStdio)
    assert s.name == "crow-mcp" and s.command == "uv"
    assert s.args == [] and s.env == []


def test_stdio_dict_keeps_explicit_args_env():
    [s] = _parse_mcp_servers(
        [
            {
                "name": "crow-mcp",
                "command": "uv",
                "args": ["run", "crow-cli", "mcp"],
                "env": [{"name": "K", "value": "V"}],
            }
        ]
    )
    assert s.args == ["run", "crow-cli", "mcp"]
    assert [(e.name, e.value) for e in s.env] == [("K", "V")]


def test_http_and_sse_route_on_explicit_type():
    http, sse = _parse_mcp_servers(
        [
            {"name": "h", "type": "http", "url": "http://x/mcp", "headers": []},
            {"name": "s", "type": "sse", "url": "http://x/sse", "headers": []},
        ]
    )
    assert isinstance(http, HttpMcpServer) and isinstance(sse, SseMcpServer)


def test_models_pass_through_untouched():
    model = McpServerStdio(name="x", command="true", args=[], env=[])
    assert _parse_mcp_servers([model]) == [model]


def test_bad_shape_is_loud():
    with pytest.raises(Exception):
        _parse_mcp_servers([{"command": "uv"}])  # no name — must NOT vanish
