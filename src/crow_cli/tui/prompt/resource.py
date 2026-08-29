from dataclasses import dataclass
import mimetypes
from pathlib import Path


@dataclass
class Resource:
    root: Path
    path: Path
    mime_type: str
    text: str | None
    data: bytes | None


class ResourceError(Exception):
    """An error occurred reading a resource."""


class ResourceNotRelative(ResourceError):
    """Attempted to read a resource, not in the project directory."""


class ResourceReadError(ResourceError):
    """Failed to read the resource."""


def load_resource(root: Path, path: Path) -> Resource:
    """Load a resource from the project directory.

    Args:
        root: The project root.
        path: Relative path within project.

    Returns:
        A resource.
    """
    resource_path = root / path

    if not resource_path.is_relative_to(root):
        raise ResourceNotRelative("Resource path is not relative to project root.")

    mime_type, encoding = mimetypes.guess_file_type(resource_path)
    if mime_type is None:
        mime_type = "application/octet-stream"

    data: bytes | None
    text: str | None

    try:
        if encoding is not None:
            data = resource_path.read_bytes()
            text = None
        else:
            data = None
            text = resource_path.read_text(encoding, errors="replace")
    except FileNotFoundError:
        raise ResourceReadError(f"File not found {str(path)!r}")
    except Exception as error:
        raise ResourceReadError(f"Failed to read {str(path)!r}; {error}")

    resource = Resource(
        root,
        resource_path,
        mime_type=mime_type,
        text=text,
        data=data,
    )
    return resource
