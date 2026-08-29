from enum import IntEnum
from functools import lru_cache
from pathlib import Path
from typing import Iterable, NamedTuple, Sequence

from textual.content import Span


SAFE_COMMANDS = {
    # Display & Output
    "echo",
    "cat",
    "less",
    "more",
    "head",
    "tail",
    "tac",
    "nl",
    # File & Directory Information
    "ls",
    "tree",
    "pwd",
    "file",
    "stat",
    "du",
    "df",
    # Search & Find
    "find",
    "locate",
    "which",
    "whereis",
    "type",
    "grep",
    "egrep",
    "fgrep",
    # Text Processing (read-only)
    "wc",
    "sort",
    "uniq",
    "cut",
    "paste",
    "column",
    "tr",
    "diff",
    "cmp",
    "comm",
    # System Information
    "whoami",
    "who",
    "w",
    "id",
    "hostname",
    "uname",
    "uptime",
    "date",
    "cal",
    "env",
    "printenv",
    # Process Information
    "ps",
    "top",
    "htop",
    "pgrep",
    "jobs",
    "pstree",
    # Network (read-only operations)
    "ping",
    "traceroute",
    "nslookup",
    "dig",
    "host",
    "netstat",
    "ss",
    "ifconfig",
    "ip",
    # View compressed files (without extracting)
    "zcat",
    "zless",
    # History & Help
    "history",
    "man",
    "help",
    "info",
    "apropos",
    "whatis",
    # Comparison & Checksums
    "md5sum",
    "sha256sum",
    "sha1sum",
    "cksum",
    "sum",
    # Other Safe Commands
    "bc",
    "expr",
    "test",
    "sleep",
    "true",
    "false",
    "yes",
    "seq",
    "basename",
    "dirname",
    "realpath",
    "readlink",
}

UNSAFE_COMMANDS = {
    # File/Directory Creation
    "mkdir",
    "touch",
    "mktemp",
    "mkfifo",
    "mknod",
    # File/Directory Deletion
    "rm",
    "rmdir",
    "shred",
    # File/Directory Moving/Copying
    "mv",
    "cp",
    "rsync",
    "scp",
    "install",
    # File Modification/Editing
    "sed",  # with -i flag
    "awk",  # can write files
    "tee",  # writes to files and stdout
    # Permissions/Ownership
    "chmod",
    "chown",
    "chgrp",
    "chattr",
    "setfacl",
    # Linking
    "ln",
    "link",
    "unlink",
    # Archive/Compression (extract/compress operations)
    "tar",
    "untar",
    "zip",
    "unzip",
    "gzip",
    "gunzip",
    "bzip2",
    "bunzip2",
    "xz",
    "unxz",
    "7z",
    "rar",
    "unrar",
    # Download Tools
    "wget",
    "curl",
    "fetch",
    "aria2c",
    # Low-level Disk Operations
    "dd",
    "truncate",
    "fallocate",
    # File Splitting
    "split",
    "csplit",
    # Synchronization
    "sync",
    # System Administration
    "useradd",
    "userdel",
    "usermod",
    "groupadd",
    "groupdel",
    "passwd",
    "mount",
    "umount",
    "mkfs",
    "fdisk",
    "parted",
    "swapon",
    "swapoff",
    # Other Potentially Dangerous
    "patch",
}


COMMAND_SPLIT = {";", "&&", "||", "|"}
CHANGE_DIRECTORY = {"cd"}


class DangerLevel(IntEnum):
    """The danger level of a command."""

    SAFE = 0  # Command is know to be generally save
    UNKNOWN = 1  # We don't know about this command
    DANGEROUS = 2  # Command is potentially dangerous (can modify filesystem)
    DESTRUCTIVE = 3  # Command is both dangerous and refers outside of project root


class CommandAtom(NamedTuple):
    """A command "atom"."""

    name: str
    """Name of the command."""
    level: DangerLevel
    """Danger level."""
    path: Path
    """The path to which this command is expected to apply."""
    span: tuple[int, int]
    """Span to highlight error."""


@lru_cache(maxsize=1024)
def detect(
    project_directory: str,
    current_working_directory: str,
    command_line: str,
    *,
    danger_style: str = "",
    destructive_style: str = "$text-error on $error-muted 70%",
) -> tuple[Sequence[Span], DangerLevel]:
    """Attempt to detect potentially destructive commands.

    Args:
        project_directory: Project directory.
        current_working_directory: Current working directory.
        command_line: Bash command.
        danger_style: Style to highlight dangerous commands.
        destructive_style: Style highlight destructive commands.

    Returns:
        A tuple of spans to highlight the command, and a `DangerLevel` enumeration.
    """
    try:
        atoms = list(
            analyze(project_directory, current_working_directory, command_line)
        )
    except OSError:
        return [], DangerLevel.UNKNOWN
    spans: list[Span] = []
    for atom in atoms:
        if atom.level == DangerLevel.DANGEROUS and danger_style:
            spans.append(Span(*atom.span, danger_style))
        elif atom.level == DangerLevel.DESTRUCTIVE and destructive_style:
            spans.append(Span(*atom.span, destructive_style))

    if atoms:
        danger_level = max(command_atom.level for command_atom in atoms)
    else:
        danger_level = DangerLevel.SAFE

    return (spans, danger_level)


def analyze(
    project_directory: str, current_working_directory: str, command_line: str
) -> Iterable[CommandAtom]:
    """Analyze a command and generate information about potentially destructive commands.

    Args:
        project_dir: The project directory.
        command_line: A bash command line.

    Yields:
        `CommandAtom` objects.
    """
    project_path = Path(project_directory).resolve()

    import bashlex
    from bashlex import ast

    def recurse_nodes(root_path: Path, nodes: list[ast.node]) -> Iterable[CommandAtom]:
        for node in nodes:
            kind: str = node.kind

            if kind == "list":
                yield from recurse_nodes(root_path, node.parts)
                return

            if kind == "operator":
                continue

            level = DangerLevel.UNKNOWN

            if not hasattr(node, "parts"):
                continue

            if node.parts:
                command_name = command_line[slice(*node.parts[0].pos)]
                if command_name in SAFE_COMMANDS:
                    level = DangerLevel.SAFE
                elif command_name in UNSAFE_COMMANDS:
                    level = DangerLevel.DANGEROUS
                parts = node.parts[1:]
            else:
                parts = node.parts
                command_name = ""

            if not parts:
                yield CommandAtom(command_name, level, root_path, node.pos)
                continue

            change_directory = command_name in CHANGE_DIRECTORY

            for command_node in parts:
                command_word = command_line[slice(*node.pos)]

                if command_node.kind == "redirect":
                    redirect = command_line[slice(*command_node.output.pos)]
                    try:
                        target_path = (
                            root_path / Path(redirect).expanduser()
                        ).resolve()
                    except OSError:
                        continue
                    if not target_path.is_relative_to(project_path):
                        yield CommandAtom(
                            "redirect",
                            DangerLevel.DESTRUCTIVE,
                            target_path,
                            command_node.pos,
                        )
                    continue

                if command_node.kind == "command":
                    yield from recurse_nodes(root_path, command_node.parts)
                    continue
                if command_word.startswith(("-", "+")):
                    continue
                word = command_line[slice(*command_node.pos)]
                if change_directory:
                    try:
                        root_path = (root_path / Path(word)).expanduser().resolve()
                    except OSError:
                        pass
                    continue

                try:
                    target_path = (root_path / Path(word)).expanduser().resolve()
                except OSError:
                    continue
                if level == DangerLevel.DANGEROUS and not target_path.is_relative_to(
                    project_path
                ):
                    # If refers to a path outside of the project, upgrade to destructive
                    level = DangerLevel.DESTRUCTIVE

                yield CommandAtom(command_word, level, target_path, node.pos)

    current_path = Path(current_working_directory)
    try:
        nodes = bashlex.parse(command_line)
    except Exception:
        # Failed to parse bash
        return

    yield from recurse_nodes(current_path, nodes)


if __name__ == "__main__":
    import os
    from rich import print

    TEST = [
        "ls;ls",
        "echo 'hello world'",
        "rm foo",
        "rm ../foo",
        "rm /",
        "cat foo > ../foo.txt",
    ]

    for test in TEST:
        print(repr(test), detect(os.getcwd(), os.getcwd(), test))
