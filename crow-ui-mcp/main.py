import os

from fastmcp import FastMCP
from fastmcp.tools.function_tool import FunctionTool
import requests


mcp = FastMCP("crow-ui-mcp")


def prompt(message: str, session_id: str, from_session_id: str = "session-123"):
    """Send a prompt message to another agent session."""
    url = f"http://localhost:45489/api/acp/sessions/{session_id}/prompt"
    headers = {"Content-Type": "application/json"}
    request_body = dict(
        blocks=[
            dict(type="text", text=message)
        ]
    )
    res = requests.post(url, headers=headers, json=request_body)
    if res.status_code == 200:
        return "Message sent"
    else:
        return "Message not sent"


# Create the tool manually so we can mutate its schema
tool = FunctionTool.from_function(prompt, name="prompt")

# Hide from_session_id from the LLM-facing schema, but keep it in the
# function signature so Pydantic still accepts it at runtime.
tool.parameters["properties"] = {
    k: v for k, v in tool.parameters["properties"].items()
    if k != "from_session_id"
}
tool.parameters["required"] = [
    k for k in tool.parameters.get("required", [])
    if k != "from_session_id"
]

mcp.add_tool(tool)

if __name__ == "__main__":
    mcp.run()
