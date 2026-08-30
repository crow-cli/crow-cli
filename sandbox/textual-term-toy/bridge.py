"""Bridge a PTY running toy.py to a websocket so riotermjs can render it.

Protocol (browser <-> bridge):
  binary frame  -> raw input bytes written to the PTY
  text frame    -> JSON control message, e.g. {"resize": [cols, rows]}
  bridge -> browser: binary frames of PTY output

Run:  uv --project . run bridge.py [port]
"""

from __future__ import annotations

import asyncio
import fcntl
import json
import os
import pty
import signal
import struct
import sys
import termios
from pathlib import Path

import websockets

HERE = Path(__file__).parent
TOY = HERE / "toy.py"


def set_winsize(fd: int, cols: int, rows: int) -> None:
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))


async def handler(ws, master_fd: int) -> None:
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[bytes] = asyncio.Queue()

    # A fresh terminal has no state; the TUI only ever sends diffs. Nudge
    # the winsize so the child (Textual) does a full repaint for this
    # client — the same trick a reconnect story needs.
    try:
        buf = fcntl.ioctl(master_fd, termios.TIOCGWINSZ, b"\x00" * 8)
        rows, cols = struct.unpack("HH", buf[:4])
        set_winsize(master_fd, max(2, cols - 1), rows)
        await asyncio.sleep(0.15)
        set_winsize(master_fd, cols, rows)
    except OSError:
        pass

    def on_readable() -> None:
        try:
            data = os.read(master_fd, 65536)
        except OSError:
            data = b""
        queue.put_nowait(data)

    loop.add_reader(master_fd, on_readable)

    async def pump_output() -> None:
        while True:
            data = await queue.get()
            if not data:
                break
            try:
                await ws.send(data)
            except websockets.ConnectionClosed:
                break

    out_task = asyncio.create_task(pump_output())
    try:
        async for message in ws:
            if isinstance(message, (bytes, bytearray)):
                os.write(master_fd, bytes(message))
            else:
                try:
                    control = json.loads(message)
                except json.JSONDecodeError:
                    continue
                if "resize" in control:
                    cols, rows = control["resize"]
                    set_winsize(master_fd, int(cols), int(rows))
    finally:
        out_task.cancel()
        loop.remove_reader(master_fd)


async def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    cols, rows = 150, 42

    # Spawn the toy in a PTY the browser will render.
    pid, master_fd = pty.fork()
    if pid == 0:  # child
        os.chdir(HERE)
        os.environ["TERM"] = "xterm-256color"
        os.execvp("uv", ["uv", "--project", ".", "run", "toy.py"])

    set_winsize(master_fd, cols, rows)
    print(f"toy pid={pid} pty fd={master_fd}", flush=True)

    async def on_connect(ws):
        await handler(ws, master_fd)

    async with websockets.serve(on_connect, "127.0.0.1", port, max_size=None):
        print(f"ws://127.0.0.1:{port}", flush=True)
        try:
            await asyncio.Future()
        finally:
            try:
                os.kill(pid, signal.SIGHUP)
            except ProcessLookupError:
                pass


if __name__ == "__main__":
    asyncio.run(main())
