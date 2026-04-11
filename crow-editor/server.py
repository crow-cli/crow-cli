"""
Crow IDE Server - Starlette-based web server.

Provides HTTP and WebSocket endpoints for the IDE.
"""

import os
from pathlib import Path

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Mount, Route, WebSocketRoute
from starlette.staticfiles import StaticFiles
from starlette.websockets import WebSocket

from acp_bridge import ACPBridge, ACPWebSocketProxy
from api.files import (
    create_file_sync,
    delete_file_sync,
    file_details_sync,
    list_files_sync,
    update_file_sync,
)
from api.terminal import TerminalHandler
from db import get_store


async def health(request: Request) -> JSONResponse:
    """Health check endpoint."""
    return JSONResponse({"status": "ok"})


async def list_files(request: Request) -> JSONResponse:
    """List files in a directory."""
    data = await request.json()
    path = data.get("path", os.environ.get("CROW_WORKSPACE", "."))
    relative_path = data.get("relative_path")

    try:
        result = list_files_sync(path, relative_path)
        return JSONResponse(result)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)


async def file_details(request: Request) -> JSONResponse:
    """Get file details and contents."""
    data = await request.json()
    path = data.get("path")

    if not path:
        return JSONResponse({"error": "path is required"}, status_code=400)

    try:
        result = file_details_sync(path)
        return JSONResponse(result)
    except FileNotFoundError as e:
        return JSONResponse({"error": str(e)}, status_code=404)


async def create_file(request: Request) -> JSONResponse:
    """Create a new file."""
    data = await request.json()
    path = data.get("path")
    contents = data.get("contents", "")

    if not path:
        return JSONResponse({"error": "path is required"}, status_code=400)

    try:
        result = create_file_sync(path, contents)
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


async def update_file(request: Request) -> JSONResponse:
    """Update file contents."""
    data = await request.json()
    path = data.get("path")
    contents = data.get("contents")

    if not path:
        return JSONResponse({"error": "path is required"}, status_code=400)
    if contents is None:
        return JSONResponse({"error": "contents is required"}, status_code=400)

    try:
        result = update_file_sync(path, contents)
        return JSONResponse(result)
    except FileNotFoundError as e:
        return JSONResponse({"error": str(e)}, status_code=404)


async def delete_file(request: Request) -> JSONResponse:
    """Delete a file."""
    data = await request.json()
    path = data.get("path")

    if not path:
        return JSONResponse({"error": "path is required"}, status_code=400)

    try:
        result = delete_file_sync(path)
        return JSONResponse(result)
    except FileNotFoundError as e:
        return JSONResponse({"error": str(e)}, status_code=404)


async def terminal_websocket(websocket: WebSocket) -> None:
    """Handle terminal WebSocket connections."""
    handler = TerminalHandler()
    await handler.handle(websocket)


async def acp_websocket(websocket: WebSocket) -> None:
    """Handle ACP WebSocket connections.

    Query params:
        url: Target WebSocket URL (e.g., ws://localhost:3000) - optional
        agent: Agent type (e.g., karla, openhands, claude)
        cwd: Working directory for the agent - required for agents to work correctly
        direct: If "true", spawn subprocess directly instead of proxying

    For karla agent without explicit URL, spawns karla-acp directly as subprocess.
    For openhands agent without explicit URL, spawns openhands acp directly as subprocess.
    For other agents or explicit URLs, proxies to the WebSocket URL.

    IMPORTANT: The cwd param determines where the agent process runs from.
    This affects file operations, git status, and all path-relative tools.
    """
    query_params = dict(websocket.query_params)
    target_url = query_params.get("url")
    agent_type = query_params.get("agent", "unknown")
    cwd = query_params.get("cwd")  # User-selected workspace directory
    use_direct = query_params.get("direct", "false").lower() == "true"

    # For karla agent, spawn directly unless URL explicitly provided
    if agent_type == "karla" and (not target_url or use_direct):
        # Use user-specified cwd, or fall back to karla directory for config
        if cwd:
            working_dir = cwd
        else:
            # Fall back to karla directory where karla.yaml config exists
            karla_dir = Path(__file__).parent.parent / "karla"
            working_dir = str(karla_dir)
        bridge = ACPBridge(["karla"], cwd=working_dir)
        await bridge.handle(websocket)
    # For crow-agent, spawn directly unless URL explicitly provided
    elif agent_type == "crow-agent" and (not target_url or use_direct):
        # Use user-specified cwd, or fall back to current directory
        if cwd:
            working_dir = cwd
        else:
            # Fall back to current directory
            working_dir = os.getcwd()
        # Find crow-agent command - try uv run first, then direct path
        crow_agent_cmd = os.environ.get(
            "CROW_AGENT_CMD", "uv run --directory crow-agent crow-agent"
        )
        bridge = ACPBridge(crow_agent_cmd.split() + ["acp"], cwd=working_dir)
        await bridge.handle(websocket)
    # For openhands agent, spawn directly unless URL explicitly provided
    elif agent_type == "openhands" and (not target_url or use_direct):
        # Use user-specified cwd, or fall back to current directory
        if cwd:
            working_dir = cwd
        else:
            # Fall back to current directory
            working_dir = os.getcwd()
        # Find openhands command - try uv run first, then direct path
        openhands_cmd = os.environ.get(
            "CROW_OPENHANDS_CMD", "uv run --directory OpenHands-CLI openhands"
        )
        bridge = ACPBridge(openhands_cmd.split() + ["acp"], cwd=working_dir)
        await bridge.handle(websocket)
    # For crow agent, spawn directly unless URL explicitly provided
    elif agent_type == "crow" and (not target_url or use_direct):
        # Use user-specified cwd, or fall back to current directory
        if cwd:
            working_dir = cwd
        else:
            # Fall back to current directory
            working_dir = os.getcwd()
        # Find crow command - it's installed via uv
        bridge = ACPBridge(["crow", "acp"], cwd=working_dir)
        await bridge.handle(websocket)
    else:
        # Proxy to external WebSocket URL
        if not target_url:
            target_url = os.environ.get("CROW_ACP_URL", "ws://localhost:3000/message")
        proxy = ACPWebSocketProxy(target_url, agent_type=agent_type)
        await proxy.handle(websocket)


# Session history API endpoints


async def list_sessions(request: Request) -> JSONResponse:
    """List all sessions."""
    store = get_store()
    data = await request.json() if request.method == "POST" else {}
    agent_type = data.get("agent_type")
    limit = data.get("limit", 100)
    offset = data.get("offset", 0)

    sessions = store.list_sessions(agent_type=agent_type, limit=limit, offset=offset)
    return JSONResponse({"sessions": sessions})


async def get_session(request: Request) -> JSONResponse:
    """Get a session by ID with all messages."""
    data = await request.json()
    session_id = data.get("session_id")

    if not session_id:
        return JSONResponse({"error": "session_id is required"}, status_code=400)

    store = get_store()
    session = store.get_session(session_id)

    if not session:
        return JSONResponse({"error": "Session not found"}, status_code=404)

    messages = store.get_session_messages(session_id)
    return JSONResponse({"session": session, "messages": messages})


async def delete_session(request: Request) -> JSONResponse:
    """Delete a session."""
    data = await request.json()
    session_id = data.get("session_id")

    if not session_id:
        return JSONResponse({"error": "session_id is required"}, status_code=400)

    store = get_store()
    deleted = store.delete_session(session_id)

    if not deleted:
        return JSONResponse({"error": "Session not found"}, status_code=404)

    return JSONResponse({"success": True})


# Frontend paths
# When installed as a package, look for data in the package installation directory
# When running from source, look relative to this file
import importlib.resources


def _get_frontend_dir() -> Path:
    """Get the frontend directory, handling both installed and source scenarios."""
    # First, try to find it as package data (installed wheel)
    try:
        with importlib.resources.files("crow-editor") as editor_dir:
            frontend_path = editor_dir / "frontend" / "dist"
            if frontend_path.is_dir():
                return Path(str(frontend_path))
    except (FileNotFoundError, AttributeError):
        pass

    # Fall back to relative path (source/development)
    relative_path = Path(__file__).parent / "frontend" / "dist"
    if relative_path.is_dir():
        return relative_path

    # Return the relative path anyway (will fail later with clear error)
    return relative_path


FRONTEND_DIR = _get_frontend_dir()
INDEX_HTML = FRONTEND_DIR / "index.html"


async def index(request: Request) -> FileResponse:
    """Serve the frontend index.html."""
    if INDEX_HTML.exists():
        return FileResponse(INDEX_HTML)
    return JSONResponse(
        {"error": "Frontend not built. Run: cd crow_ide/frontend && pnpm build"},
        status_code=404,
    )


async def validate_directory(request: Request) -> JSONResponse:
    """Validate that a path is a valid directory."""
    data = await request.json()
    path = data.get("path", "")

    if not path:
        return JSONResponse(
            {"valid": False, "error": "Path is required"}, status_code=400
        )

    # Expand ~ to home directory
    expanded = os.path.expanduser(path)

    # Resolve to absolute path
    try:
        absolute = os.path.abspath(expanded)
    except Exception as e:
        return JSONResponse({"valid": False, "error": str(e)}, status_code=400)

    if os.path.isdir(absolute):
        return JSONResponse({"valid": True, "path": absolute})

    return JSONResponse(
        {"valid": False, "error": "Not a valid directory"}, status_code=400
    )


async def list_directories(request: Request) -> JSONResponse:
    """List subdirectories in a directory for the directory browser."""
    data = await request.json()
    path = data.get("path", os.path.expanduser("~"))

    # Expand ~ to home directory
    expanded = os.path.expanduser(path)

    try:
        absolute = os.path.abspath(expanded)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    if not os.path.isdir(absolute):
        return JSONResponse({"error": "Not a valid directory"}, status_code=400)

    try:
        entries = []
        for entry in sorted(os.listdir(absolute)):
            # Skip hidden directories
            if entry.startswith("."):
                continue
            full_path = os.path.join(absolute, entry)
            if os.path.isdir(full_path):
                entries.append(
                    {
                        "name": entry,
                        "path": full_path,
                    }
                )
        return JSONResponse(
            {
                "path": absolute,
                "parent": os.path.dirname(absolute) if absolute != "/" else None,
                "directories": entries,
            }
        )
    except PermissionError:
        return JSONResponse({"error": "Permission denied"}, status_code=403)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# Define routes
routes = [
    Route("/", index, methods=["GET"]),
    Route("/api/health", health, methods=["GET"]),
    # File operations
    Route("/api/files/list", list_files, methods=["POST"]),
    Route("/api/files/details", file_details, methods=["POST"]),
    Route("/api/files/create", create_file, methods=["POST"]),
    Route("/api/files/update", update_file, methods=["POST"]),
    Route("/api/files/delete", delete_file, methods=["POST"]),
    # Session history
    Route("/api/sessions/list", list_sessions, methods=["POST"]),
    Route("/api/sessions/get", get_session, methods=["POST"]),
    Route("/api/sessions/delete", delete_session, methods=["POST"]),
    # Directory operations
    Route("/api/directories/validate", validate_directory, methods=["POST"]),
    Route("/api/directories/list", list_directories, methods=["POST"]),
    # WebSocket endpoints
    WebSocketRoute("/terminal", terminal_websocket),
    WebSocketRoute("/acp", acp_websocket),
]

# Add static file serving if frontend is built
if FRONTEND_DIR.exists():
    routes.append(
        Mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="assets")
    )

# Create app
app = Starlette(routes=routes, debug=True)
