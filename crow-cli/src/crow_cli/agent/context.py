import json
import os
import re
from typing import Any
from urllib.parse import urlparse
from urllib.request import url2pathname

from directory_tree import DisplayTree


def maximal_deserialize(data):
    """
    Recursively drills into dictionaries and lists,
    deserializing any JSON strings it finds until
    no more strings can be converted to objects.
    """
    # 1. If it's a string, try to decode it
    if isinstance(data, str):
        try:
            # We strip it to avoid trying to load plain numbers/bools
            # as JSON if they are just "1" or "true"
            if data.startswith(("{", "[")):
                decoded = json.loads(data)
                # If it successfully decoded, recurse on the result
                # (to handle nested-serialized strings)
                return maximal_deserialize(decoded)
        except json.JSONDecodeError, TypeError, ValueError:
            # Not valid JSON, return the original string
            pass
        return data

    # 2. If it's a dictionary, recurse on its values
    elif isinstance(data, dict):
        return {k: maximal_deserialize(v) for k, v in data.items()}

    # 3. If it's a list, recurse on its elements
    elif isinstance(data, list):
        return [maximal_deserialize(item) for item in data]

    # 4. Return anything else as-is (int, float, bool, None)
    return data


def number_lines(content: str) -> list[str]:
    return [f"{k:6}\t{line}" for k, line in enumerate(content.split("\n"))]


def context_fetcher(uri: str) -> str:

    res = find_line_numbers(uri)
    if res["status"] == "success":
        # pull out everything before the #L
        file_uri = uri.split("#L")[0]
        file_path = uri_to_path(file_uri)
        with open(file_path, "r") as f:
            content = f.read()
        split_content = number_lines(content)
        start = res["start"]
        end = res["end"]
        if start is not None and end is not None:
            content = split_content[start - 1 : end]
        elif start is not None:
            content = split_content[start - 1 :]
        elif end is not None:
            content = split_content[:end]
        else:
            content = split_content
    else:  # no line numbers, read whole file
        file_path = uri_to_path(uri)
        with open(file_path, "r") as f:
            content = f.read()
        content = number_lines(content)

    return "\n".join([file_path] + content)


def uri_to_path(uri: str) -> str:
    parsed = urlparse(uri)
    return url2pathname(parsed.path)


def find_line_numbers(uri: str) -> dict[str, Any]:
    pattern = r"#L(\d+)?(?::(\d+))?$"
    match = re.search(pattern, uri)
    response = {}
    if match:
        start, end = match.groups()
        response["status"] = "success"
        response["start"] = int(start) if start else None
        response["end"] = int(end) if end else None
    else:
        response["status"] = "failure"
        response["start"] = None
        response["end"] = None
    return response


def get_directory_tree(cwd: str) -> str:
    """Returns a string representation of the directory tree rooted at cwd."""
    ignores = ["node_modules", "*.egg_info", "__pycache__", ".venv", "refs"]
    tree = DisplayTree(stringRep=True, dirPath=cwd, ignoreList=ignores, maxDepth=3.0)
    return tree
