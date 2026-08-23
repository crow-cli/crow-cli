"""Edit file tool - performs string replacements with fuzzy matching.

Implements 9 cascading matchers ported from OpenCode/crow_agent:
1. Simple (exact match)
2. Line-trimmed
3. Block anchor (first/last line with fuzzy middle)
4. Whitespace normalized
5. Indentation flexible
6. Escape normalized
7. Trimmed boundary
8. Context-aware (50% middle match)
9. Multi-occurrence
"""

import os
import re
from collections.abc import Generator
from pathlib import Path

from crow_cli.mcp.server.app import mcp

# Similarity thresholds for block anchor fallback matching
SINGLE_CANDIDATE_SIMILARITY_THRESHOLD = 0.0
MULTIPLE_CANDIDATES_SIMILARITY_THRESHOLD = 0.3


def _get_working_dir() -> Path:
    """Get the current working directory."""
    return Path(os.getcwd()).resolve()


def _resolve_path(path: str) -> Path:
    """Resolve a path to its canonical absolute form.

    Relative paths are resolved against the current working directory. There is
    no working-directory sandbox here: access control is delegated to the
    operating system. The agent runs as the local user, so it can edit exactly
    the files that user's Unix permissions allow (and nothing else). This keeps
    ``edit`` consistent with ``read``, ``write``, and ``terminal``, none of
    which impose a cwd restriction.
    """
    working_dir = _get_working_dir()
    requested = Path(path)
    full_path = requested if requested.is_absolute() else working_dir / requested

    try:
        return full_path.resolve()
    except OSError as e:
        raise ValueError(f"Cannot resolve path: {e}")


def levenshtein(a: str, b: str) -> int:
    """Calculate Levenshtein distance between two strings."""
    if not a or not b:
        return max(len(a), len(b))

    # Create matrix
    rows = len(a) + 1
    cols = len(b) + 1
    matrix = [[0] * cols for _ in range(rows)]

    # Initialize first row and column
    for i in range(rows):
        matrix[i][0] = i
    for j in range(cols):
        matrix[0][j] = j

    # Fill in the rest
    for i in range(1, rows):
        for j in range(1, cols):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            matrix[i][j] = min(
                matrix[i - 1][j] + 1,  # deletion
                matrix[i][j - 1] + 1,  # insertion
                matrix[i - 1][j - 1] + cost,  # substitution
            )

    return matrix[rows - 1][cols - 1]


# ==================== Cascading Replacers ====================


def simple_replacer(content: str, find: str) -> Generator[str, None, None]:
    """1. Simple exact string match."""
    if find in content:
        yield find


def line_trimmed_replacer(content: str, find: str) -> Generator[str, None, None]:
    """2. Match lines by trimmed content."""
    original_lines = content.split("\n")
    search_lines = find.split("\n")

    # Remove trailing empty line if present
    if search_lines and search_lines[-1] == "":
        search_lines = search_lines[:-1]

    for i in range(len(original_lines) - len(search_lines) + 1):
        matches = True
        for j, search_line in enumerate(search_lines):
            if original_lines[i + j].strip() != search_line.strip():
                matches = False
                break

        if matches:
            # Calculate byte positions
            start_idx = sum(len(original_lines[k]) + 1 for k in range(i))
            end_idx = start_idx
            for k in range(len(search_lines)):
                end_idx += len(original_lines[i + k])
                if k < len(search_lines) - 1:
                    end_idx += 1  # newline
            yield content[start_idx:end_idx]


def block_anchor_replacer(content: str, find: str) -> Generator[str, None, None]:
    """3. Match blocks using first/last line as anchors with fuzzy middle."""
    original_lines = content.split("\n")
    search_lines = find.split("\n")

    if len(search_lines) < 3:
        return

    if search_lines and search_lines[-1] == "":
        search_lines = search_lines[:-1]

    first_line_search = search_lines[0].strip()
    last_line_search = search_lines[-1].strip()

    # Find all candidate positions
    candidates: list[tuple[int, int]] = []
    for i, line in enumerate(original_lines):
        if line.strip() != first_line_search:
            continue
        # Look for matching last line
        for j in range(i + 2, len(original_lines)):
            if original_lines[j].strip() == last_line_search:
                candidates.append((i, j))
                break

    if not candidates:
        return

    # Calculate similarity for candidates
    threshold = (
        SINGLE_CANDIDATE_SIMILARITY_THRESHOLD
        if len(candidates) == 1
        else MULTIPLE_CANDIDATES_SIMILARITY_THRESHOLD
    )

    best_match: tuple[int, int] | None = None
    max_similarity = -1.0

    for start_line, end_line in candidates:
        actual_size = end_line - start_line + 1
        lines_to_check = min(len(search_lines) - 2, actual_size - 2)

        if lines_to_check > 0:
            similarity = 0.0
            for j in range(1, min(len(search_lines) - 1, actual_size - 1)):
                orig = original_lines[start_line + j].strip()
                search = search_lines[j].strip()
                max_len = max(len(orig), len(search))
                if max_len > 0:
                    dist = levenshtein(orig, search)
                    similarity += 1.0 - dist / max_len
            similarity /= lines_to_check
        else:
            similarity = 1.0

        if similarity > max_similarity:
            max_similarity = similarity
            best_match = (start_line, end_line)

    if max_similarity >= threshold and best_match:
        start_line, end_line = best_match
        start_idx = sum(len(original_lines[k]) + 1 for k in range(start_line))
        end_idx = start_idx
        for k in range(start_line, end_line + 1):
            end_idx += len(original_lines[k])
            if k < end_line:
                end_idx += 1
        yield content[start_idx:end_idx]


def whitespace_normalized_replacer(
    content: str, find: str
) -> Generator[str, None, None]:
    """4. Match with normalized whitespace using regex for exact content extraction."""
    words = find.strip().split()
    if not words:
        return

    # Create a regex pattern that treats any sequence of whitespace (including newlines)
    # as a flexible gap between the exact words we are looking for.
    pattern = r"\s+".join(re.escape(w) for w in words)

    # re.finditer will find the exact string inside `content` that matches this sequence
    for match in re.finditer(pattern, content):
        yield match.group(0)


def indentation_flexible_replacer(
    content: str, find: str
) -> Generator[str, None, None]:
    """5. Match ignoring common indentation."""

    def remove_indentation(text: str) -> str:
        lines = text.split("\n")
        non_empty = [ln for ln in lines if ln.strip()]
        if not non_empty:
            return text

        min_indent = min(len(ln) - len(ln.lstrip()) for ln in non_empty)
        return "\n".join(ln if not ln.strip() else ln[min_indent:] for ln in lines)

    normalized_find = remove_indentation(find)
    content_lines = content.split("\n")
    find_lines = find.split("\n")

    for i in range(len(content_lines) - len(find_lines) + 1):
        block = "\n".join(content_lines[i : i + len(find_lines)])
        if remove_indentation(block) == normalized_find:
            yield block


def escape_normalized_replacer(content: str, find: str) -> Generator[str, None, None]:
    """6. Match with escape sequences normalized."""
    escape_map = {
        r"\n": "\n",
        r"\t": "\t",
        r"\r": "\r",
        r"\'": "'",
        r"\"": '"',
        r"\\": "\\",
    }

    def unescape(s: str) -> str:
        result = s
        for escaped, unescaped in escape_map.items():
            result = result.replace(escaped, unescaped)
        return result

    unescaped_find = unescape(find)
    yielded = set()

    if unescaped_find in content:
        yield unescaped_find
        yielded.add(unescaped_find)

    # Also try finding escaped versions
    content_lines = content.split("\n")
    find_lines = unescaped_find.split("\n")

    for i in range(len(content_lines) - len(find_lines) + 1):
        block = "\n".join(content_lines[i : i + len(find_lines)])
        if unescape(block) == unescaped_find and block not in yielded:
            yield block
            yielded.add(block)


def trimmed_boundary_replacer(content: str, find: str) -> Generator[str, None, None]:
    """7. Match with trimmed boundaries."""
    trimmed = find.strip()
    if trimmed == find:
        return  # Already trimmed

    yielded = set()

    if trimmed in content:
        yield trimmed
        yielded.add(trimmed)

    # Also try block matching
    content_lines = content.split("\n")
    find_lines = find.split("\n")

    for i in range(len(content_lines) - len(find_lines) + 1):
        block = "\n".join(content_lines[i : i + len(find_lines)])
        if block.strip() == trimmed and block not in yielded:
            yield block
            yielded.add(block)


def context_aware_replacer(content: str, find: str) -> Generator[str, None, None]:
    """8. Match using first/last lines as context with 50% middle match."""
    find_lines = find.split("\n")
    if len(find_lines) < 3:
        return

    if find_lines and find_lines[-1] == "":
        find_lines = find_lines[:-1]

    content_lines = content.split("\n")
    first_line = find_lines[0].strip()
    last_line = find_lines[-1].strip()

    for i, line in enumerate(content_lines):
        if line.strip() != first_line:
            continue

        # Calculate the expected end line based on find_lines length
        expected_end = i + len(find_lines) - 1
        if expected_end >= len(content_lines):
            continue

        # Check if the last line matches at the expected position
        if content_lines[expected_end].strip() != last_line:
            continue

        block_lines = content_lines[i : expected_end + 1]

        # Check middle lines for 50% match
        matching = 0
        total = 0

        for k in range(1, len(block_lines) - 1):
            block_ln = block_lines[k].strip()
            find_ln = find_lines[k].strip()
            if block_ln or find_ln:
                total += 1
                if block_ln == find_ln:
                    matching += 1

        if total == 0 or matching / total >= 0.5:
            yield "\n".join(block_lines)


def multi_occurrence_replacer(content: str, find: str) -> Generator[str, None, None]:
    """9. Yield all exact matches."""
    if find in content:
        yield find


# All replacers in order
REPLACERS = [
    simple_replacer,
    line_trimmed_replacer,
    block_anchor_replacer,
    whitespace_normalized_replacer,
    indentation_flexible_replacer,
    escape_normalized_replacer,
    trimmed_boundary_replacer,
    context_aware_replacer,
    multi_occurrence_replacer,
]


def replace(
    content: str, old_string: str, new_string: str, replace_all: bool = False
) -> str:
    """Replace old_string with new_string using cascading fuzzy matchers based on precise spans."""
    if old_string == new_string:
        raise ValueError("old_string and new_string must be different")

    all_matches: list[tuple[int, int]] = []

    for replacer in REPLACERS:
        # Use a set to prevent duplicate string yields from causing false multiple matches
        found_in_this_step = set()

        for search_text in replacer(content, old_string):
            start = 0
            while True:
                idx = content.find(search_text, start)
                if idx == -1:
                    break
                found_in_this_step.add((idx, idx + len(search_text)))
                # Move past this match to avoid overlapping matches
                start = idx + len(search_text)

        if found_in_this_step:
            all_matches = list(found_in_this_step)
            break  # We found the best fuzziness level, stop cascading

    if not all_matches:
        raise ValueError("old_string not found in file")

    # Sort in reverse order so applying the replacement doesn't invalidate subsequent indices
    all_matches.sort(key=lambda x: x[0], reverse=True)

    if len(all_matches) > 1 and not replace_all:
        raise ValueError(
            f"old_string found {len(all_matches)} times. Provide more context to identify the correct match."
        )

    # Apply all matched replacements back-to-front
    new_content = content
    for start, end in all_matches:
        new_content = new_content[:start] + new_string + new_content[end:]

    return new_content


@mcp.tool
async def edit(
    file_path: str,
    old_string: str,
    new_string: str,
    replace_all: bool = False,
) -> str:
    """Performs precise string replacements in files.

    Usage:
    - The file_path parameter must be an absolute path
    - You must read the file first before editing and pay attention to whitespace
    - old_string MUST BE unique - provide more context to make it unique or this will FAIL
    - Use replace_all=true to replace all occurrences (useful for renaming)
    - Prioritize editing existing files over full rewrites

    Args:
        file_path: The absolute path to the file to edit
        old_string: The text to replace (MUST BE UNIQUE IF NOT USING replace_all)
        new_string: The text to replace it with
        replace_all: Replace all occurrences (default false)

    Returns:
        Success message or error message
    """
    if old_string == new_string:
        return "Error: old_string and new_string must be different"

    try:
        path = _resolve_path(file_path)
    except ValueError as e:
        return f"Error: {e}"

    if not path.exists():
        return f"Error: File does not exist: {path}"
    if not path.is_file():
        return f"Error: Path is a directory: {path}"

    # Read current content
    try:
        content = path.read_text(encoding="utf-8")
    except PermissionError:
        return f"Error: Permission denied: {path}"
    except OSError as e:
        return f"Error: Failed to read file: {e}"

    # Perform fuzzy replacement
    try:
        new_content = replace(content, old_string, new_string, replace_all)
    except ValueError as e:
        return f"Error: {e}"

    # Write back
    try:
        path.write_text(new_content, encoding="utf-8")
    except PermissionError:
        return f"Error: Permission denied: {path}"
    except OSError as e:
        return f"Error: Failed to write file: {e}"

    # Since the `replace` function now accurately determines the match count natively,
    # we can determine replacements based on `replace_all` logic more cleanly,
    # but the simplest way is just checking string length changes or just stating success.
    if replace_all:
        return f"Successfully made replacements in {path}"

    return f"Successfully edited {path}"
