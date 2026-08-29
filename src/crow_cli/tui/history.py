from typing import TypedDict
import asyncio
import json
from pathlib import Path
from time import time

import rich.repr

from crow_cli.tui.complete import Complete


class HistoryEntry(TypedDict):
    """An entry in the history file."""

    input: str
    timestamp: float


@rich.repr.auto
class History:
    """Manages a history file."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lines: list[str] = []
        self._opened: bool = False
        self._current: str | None = None
        self.complete = Complete()

    def __rich_repr__(self) -> rich.repr.Result:
        yield self.path

    @property
    def current(self) -> str | None:
        return self._current

    @current.setter
    def current(self, current: str) -> None:
        self._current = current

    @property
    def size(self) -> int:
        return len(self._lines)

    async def open(self) -> bool:
        """Open the history file, read initial lines.

        Returns:
            `True` if lines were read, otherwise `False`.
        """
        if self._opened:
            return True

        def read_history() -> bool:
            """Read the history file (in a thread).

            Returns:
                `True` on success.
            """
            try:
                self.path.touch(exist_ok=True)
                with self.path.open("r") as history_file:
                    self._lines = history_file.readlines()

                inputs: list[str] = []
                for line in self._lines:
                    if (input := json.loads(line).get("input")) is not None:
                        inputs.append(input.split(" ", 1)[0])
                self.complete.add_words(inputs)
            except Exception:
                return False
            return True

        self._opened = await asyncio.to_thread(read_history)
        return self._opened

    async def append(self, input: str) -> bool:
        """Append a history entry.

        Args:
            text: Text in the history.
            shell: Boolean that indicates if the text is shell (`True`) or prompt (`False`).

        Returns:
            `True` on success.
        """

        if not input:
            return True
        self.complete.add_words([input.split(" ")[0]])

        def write_line() -> bool:
            """Append a line to the history.

            Returns:
                `True` on success, `False` if write failed.
            """
            history_entry: HistoryEntry = {
                "input": input,
                "timestamp": time(),
            }
            line = json.dumps(history_entry)
            self._lines.append(line)
            try:
                with self.path.open("a") as history_file:
                    history_file.write(f"{line}\n")
            except Exception:
                return False
            self._current = None
            return True

        if not self._opened:
            await self.open()

        return await asyncio.to_thread(write_line)

    async def get_entry(self, index: int) -> HistoryEntry:
        """Get a history entry via its index.

        Args:
            index: Index of entry. 0 for the last entry, negative indexes for previous entries.

        Returns:
            A history entry dict.
        """
        if index > 0:
            raise IndexError("History indices must be 0 or negative.")
        if not self._opened:
            await self.open()

        if index == 0:
            return {"input": self.current or "", "timestamp": time()}
        try:
            entry_line = self._lines[index]
        except IndexError:
            raise IndexError(f"No history entry at index {index}")
        history_entry: HistoryEntry = json.loads(entry_line)
        return history_entry
