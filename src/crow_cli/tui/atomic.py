import tempfile
import os


class AtomicWriteError(Exception):
    """An Atomic write failed."""


def write(path: str, content: str) -> None:
    """Write a file in an atomic manner.

    Args:
        filename: Filename of new file.
        content: Content to write.

    """
    path = os.path.abspath(path)
    dir_name = os.path.dirname(path) or "."
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            delete=False,
            dir=dir_name,
            prefix=f".{os.path.basename(path)}_tmp_",
        ) as temporary_file:
            temporary_file.write(content)
            temp_name = temporary_file.name
    except Exception as error:
        raise AtomicWriteError(
            f"Failed to write {path!r}; error creating temporary file: {error}"
        )

    try:
        os.replace(temp_name, path)  # Atomic on POSIX and Windows
    except Exception as error:
        raise AtomicWriteError(f"Failed to write {path!r}; {error}")
