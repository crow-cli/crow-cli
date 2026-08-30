"""Resize-semantics regression tests for the ANSI emulator.

The oracle is pyte: fullscreen (alternate-screen) programs such as helix
address rows absolutely (CUP), so on resize the emulator must use
real-terminal grid semantics — truncate columns on width shrink, drop rows
from the top on height shrink — and NEVER fold stale lines (a folded line
shifts every row address below it, which is exactly the garbled-helix bug
these tests pin down).
"""

import pyte
import pytest

from crow_cli.tui.ansi import TerminalState


async def dummy_stdin(text: str) -> bool:
    return True


def paint_grid(width: int, height: int, top_row: int = 0) -> str:
    """A helix-shaped repaint: CUP-per-row + SGR + full-width text."""
    chunks = []
    for row in range(top_row, height):
        marker = f"{row + 1:>3}"
        text = marker + " " + "x" * (width - 8) + " EOL"
        chunks.append(f"\x1b[{row + 1};1H\x1b[38;5;{row % 255 + 1}m{text}")
    return "".join(chunks)


def our_rows(state: TerminalState) -> list[str]:
    return [fold.content.plain.rstrip() for fold in state.alternate_buffer.folded_lines]


def pyte_rows(screen: pyte.Screen) -> list[str]:
    rows = []
    for y in range(screen.lines):
        line = screen.buffer[y]
        rows.append(
            "".join(
                line[x].data if x in line else screen.default_char
                for x in range(screen.columns)
            ).rstrip()
        )
    return rows


async def test_alternate_resize_and_scroll_matches_pyte() -> None:
    """Paint -> shrink resize -> repaint -> scroll repaints, 0 mismatches."""
    state = TerminalState(dummy_stdin, width=40, height=12)
    state.alternate_screen = True
    screen = pyte.Screen(40, 12)
    stream = pyte.Stream(screen)

    # Initial paint at 40x12
    paint = paint_grid(40, 12)
    await state.write(paint)
    stream.feed(paint)
    assert our_rows(state) == pyte_rows(screen)

    # Shrink to 30x8 (both width and height)
    state.update_size(30, 8)
    screen.resize(lines=8, columns=30)

    # Program repaints on SIGWINCH at the new size
    paint = paint_grid(30, 8)
    await state.write(paint)
    stream.feed(paint)
    assert our_rows(state) == pyte_rows(screen)

    # Holding `down`: helix repaints the full grid for every scroll step
    for scroll_step in range(1, 6):
        paint = paint_grid(30, 8, top_row=scroll_step)
        await state.write(paint)
        stream.feed(paint)
        assert our_rows(state) == pyte_rows(screen)


async def test_width_shrink_truncates_and_keeps_row_addressing() -> None:
    state = TerminalState(dummy_stdin, width=40, height=12)
    state.alternate_screen = True
    await state.write(paint_grid(40, 12))

    state.update_size(30, None)

    buffer = state.alternate_buffer
    # No folding: one buffer line per grid row, 1:1 fold index
    assert len(buffer.lines) == 12
    assert len(buffer.folded_lines) == 12
    assert buffer.line_to_fold == list(range(12))
    for fold in buffer.folded_lines:
        assert fold.content.cell_length <= 30
    # Truncated at the right, not reflowed
    assert buffer.lines[0].content.plain == "  1 " + "x" * 26

    # CUP row addressing still lands on the right grid row
    await state.write("\x1b[3;1HX")
    assert buffer.lines[2].content.plain.startswith("X")
    assert buffer.lines[1].content.plain.startswith("  2")
    assert buffer.lines[3].content.plain.startswith("  4")


async def test_height_shrink_drops_rows_from_top() -> None:
    state = TerminalState(dummy_stdin, width=40, height=12)
    state.alternate_screen = True
    await state.write(paint_grid(40, 12))

    state.update_size(None, 8)

    buffer = state.alternate_buffer
    assert len(buffer.lines) == 8
    # Rows 1-4 dropped from the top; row 5 is now grid row 1
    assert buffer.lines[0].content.plain.startswith("  5")
    assert buffer.lines[-1].content.plain.startswith(" 12")
    # CUP row 1 now addresses the (old) fifth row
    await state.write("\x1b[1;1HX")
    assert buffer.lines[0].content.plain.startswith("X")


async def test_height_grow_pads_blank_rows_at_bottom() -> None:
    state = TerminalState(dummy_stdin, width=40, height=12)
    state.alternate_screen = True
    await state.write(paint_grid(40, 12))

    state.update_size(None, 16)

    buffer = state.alternate_buffer
    assert len(buffer.lines) == 16
    assert buffer.lines[0].content.plain.startswith("  1")
    assert all(not line.content.plain.strip() for line in buffer.lines[12:])


async def test_scrollback_still_folds_on_width_shrink() -> None:
    """The normal screen keeps presentation folding (a chat feature)."""
    state = TerminalState(dummy_stdin, width=40, height=24)
    await state.write("word " * 20 + "\r\n")

    state.update_size(20, None)

    buffer = state.scrollback_buffer
    assert len(buffer.lines) == 1
    assert len(buffer.folded_lines) > 1
