"""Tests for iterative refinement: XML parsing + MCP tool invocation.

Usage:
    cd /home/thomas/src/crow-ai/crow-cli/sandbox/repl-agent
    uv --project . run pytest test_iterative_refinement.py -v
"""

import pytest
import tempfile
from pathlib import Path

from iterative_refinement import (
    CritiqueResult,
    parse_critique_response,
    build_consolidated_summary,
)
from client import stdio_mcp, ReplClient

# ===========================================================================
# XML parsing tests
# ===========================================================================


class TestParseCritiqueResponse:
    def test_valid_xml_complete(self):
        text = """<critique>
  <score>0.9</score>
  <task_complete>COMPLETE</task_complete>
  <summary>All criteria met.</summary>
</critique>"""
        result = parse_critique_response(text)
        assert result.score == 0.9
        assert result.task_complete is True
        assert "All criteria met" in result.summary

    def test_valid_xml_incomplete(self):
        text = """<critique>
  <score>0.4</score>
  <task_complete>INCOMPLETE</task_complete>
  <summary>Missing type hints.</summary>
</critique>"""
        result = parse_critique_response(text)
        assert result.score == 0.4
        assert result.task_complete is False
        assert "Missing type hints" in result.summary

    def test_xml_with_true(self):
        """Some models say TRUE instead of COMPLETE."""
        text = "<score>0.8</score>\n<task_complete>TRUE</task_complete>\n<summary>Good</summary>"
        result = parse_critique_response(text)
        assert result.task_complete is True

    def test_partial_xml_missing_score(self):
        text = """<critique>
  <task_complete>COMPLETE</task_complete>
  <summary>Looks fine</summary>
</critique>"""
        result = parse_critique_response(text)
        assert result.score == 0.0
        assert result.task_complete is True

    def test_partial_xml_missing_summary(self):
        text = "<score>0.7</score>\n<task_complete>COMPLETE</task_complete>"
        result = parse_critique_response(text)
        assert result.score == 0.7
        assert result.task_complete is True
        assert result.summary == "(no summary)"

    def test_completely_unparseable(self):
        """LLM ignores XML format entirely."""
        text = "Looks good to me!"
        result = parse_critique_response(text)
        assert result.score == 0.0
        assert result.task_complete is False
        assert result.summary == "(no summary)"
        assert result.raw == text

    def test_xml_with_extra_text(self):
        """LLM adds conversational text around the XML."""
        text = """Here is my evaluation:

<critique>
  <score>0.85</score>
  <task_complete>COMPLETE</task_complete>
  <summary>Well done.</summary>
</critique>

Let me know if you need anything else."""
        result = parse_critique_response(text)
        assert result.score == 0.85
        assert result.task_complete is True

    def test_multiline_summary(self):
        text = """<critique>
  <score>0.6</score>
  <task_complete>INCOMPLETE</task_complete>
  <summary>Issue 1: No docstrings
Issue 2: No type hints
Please fix.</summary>
</critique>"""
        result = parse_critique_response(text)
        assert "Issue 1" in result.summary
        assert "Issue 2" in result.summary
        assert "Please fix" in result.summary

    def test_raw_preserved(self):
        text = "raw garbage <score>0.5</score>"
        result = parse_critique_response(text)
        assert result.raw == text


# ===========================================================================
# build_consolidated_summary tests
# ===========================================================================


class TestBuildConsolidatedSummary:
    def test_basic_summary(self):
        summaries = [
            {
                "iteration": 1,
                "worker_summary": "Created calculator.py",
                "critique": CritiqueResult(
                    score=0.8, task_complete=True, summary="All good"
                ),
            }
        ]
        result = build_consolidated_summary("Build calculator", ["has add"], summaries)
        assert "Build calculator" in result
        assert "has add" in result
        assert "0.8" in result
        assert "COMPLETE" in result
        assert "Iteration 1" in result

    def test_multiple_iterations(self):
        summaries = [
            {
                "iteration": 1,
                "worker_summary": "Initial attempt",
                "critique": CritiqueResult(
                    score=0.4, task_complete=False, summary="Missing docs"
                ),
            },
            {
                "iteration": 2,
                "worker_summary": "Added docs",
                "critique": CritiqueResult(
                    score=0.9, task_complete=True, summary="Done"
                ),
            },
        ]
        result = build_consolidated_summary("Task", ["c1"], summaries)
        assert "Iteration 1" in result
        assert "Iteration 2" in result
        assert "Missing docs" in result
        assert "Done" in result
        assert "Iterations completed:** 2" in result

    def test_no_iterations(self):
        result = build_consolidated_summary("Task", ["c1"], [])
        assert "Iterations completed:** 0" in result


# ===========================================================================
# MCP tool invocation tests via FastMCP Client
# ===========================================================================


class TestMCPToolInvocation:
    """Test MCP tools using FastMCP's in-process Client."""

    @pytest.fixture
    def mcp_instance(self):
        from iterative_refinement_mcp import mcp

        return mcp

    async def test_list_tools(self, mcp_instance):
        """Verify the refine tool is registered."""
        from fastmcp.client import Client

        async with Client(mcp_instance) as client:
            tools = await client.list_tools()
            tool_names = [t.name for t in tools]
            assert "refine" in tool_names

    async def test_refine_tool_schema(self, mcp_instance):
        """Verify refine tool has expected parameters."""
        from fastmcp.client import Client

        async with Client(mcp_instance) as client:
            tools = await client.list_tools()
            refine_tool = next(t for t in tools if t.name == "refine")
            input_schema = refine_tool.inputSchema
            assert "task" in input_schema["properties"]
            assert "criteria" in input_schema["properties"]
            assert "max_iterations" in input_schema["properties"]
            assert "cwd" in input_schema["properties"]

    async def test_refine_runs_without_error(self, mcp_instance):
        """Calling refine actually spawns agents and returns a consolidated summary."""
        from fastmcp.client import Client
        async with Client(mcp_instance) as client:
            result = await client.call_tool(
                name="refine",
                arguments={
                    "task": "Do nothing",
                    "criteria": ["criterion"],
                    "max_iterations": 0,
                },
            )
            # CallToolResult wraps the string output
            text = result.data
            assert "Iterative Refinement Report" in text
            assert "Do nothing" in text


# ===========================================================================
# MCP client passing tests
# ===========================================================================

class TestMCPClientPassing:
    """Test that MCP server configs are properly passed through ReplClient."""

    def test_stdio_mcp_helper(self):
        mcp = stdio_mcp(
            "test-server",
            "uv", "--project", ".", "run", "server.py",
            env={"FOO": "bar"},
        )
        assert mcp.name == "test-server"
        assert mcp.command == "uv"
        assert mcp.args == ["--project", ".", "run", "server.py"]
        assert len(mcp.env) == 1
        assert mcp.env[0].name == "FOO"
        assert mcp.env[0].value == "bar"

    def test_stdio_mcp_no_env(self):
        mcp = stdio_mcp("minimal", "echo", "hello")
        assert mcp.name == "minimal"
        assert mcp.command == "echo"
        assert mcp.args == ["hello"]
        assert mcp.env == []

    def test_repl_client_accepts_mcp_servers(self):
        mcp = stdio_mcp("refinement", "uv", "run", "mcp.py")
        client = ReplClient(
            "uv", "--project", ".", "run", "main.py",
            mcp_servers=[mcp],
        )
        assert len(client.mcp_servers) == 1
        assert client.mcp_servers[0].name == "refinement"

    def test_repl_client_defaults_to_empty_mcp_servers(self):
        client = ReplClient("uv", "--project", ".", "run", "main.py")
        assert client.mcp_servers == []
