"""Write file tool - creates or overwrites files."""

from pathlib import Path

from crow_cli.mcp.server.main import mcp


@mcp.tool
async def write(
    file_path: str,
    content: str,
) -> str:
    """Writes content to a file, creating it if it doesn't exist or overwriting if it does.

    Args:
        file_path: The absolute path to the file to write. NOT OPTIONAL.
        content: The content to write to the file.

    Returns:
        Success message or error message
    """
    path = Path(file_path)

    # Create parent directories if needed
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        return f"Error: Permission denied creating directory: {path.parent}"
    except OSError as e:
        return f"Error: Failed to create directory: {e}"

    # Write file
    try:
        path.write_text(content, encoding="utf-8")
    except PermissionError:
        return f"Error: Permission denied: {path}"
    except OSError as e:
        return f"Error: Failed to write file: {e}"

    lines = content.count("\n") + 1
    return f"Successfully wrote {lines} lines to {path}"
