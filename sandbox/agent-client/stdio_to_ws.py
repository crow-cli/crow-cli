"""
stdio-to-WebSocket bridge.

Bridges between a subprocess (stdio) and WebSocket.
Used to spawn ACP agents (which speak stdio) and communicate via WebSocket.

Usage:
    uv run stdio_to_ws.py --port 8765 <command> <args>
    
Example:
    uv run stdio_to_ws.py --port 8765 uv run echo_agent.py
"""

import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Optional

import websockets
from websockets.server import WebSocketServerProtocol

# Log to file, NOT stdio
log_file = Path(__file__).parent / "stdio_to_ws.log"
logging.basicConfig(
    filename=str(log_file),
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class StdioToWsBridge:
    """Bridge between WebSocket and subprocess stdio."""

    def __init__(self, command: list[str], port: int = 8765, host: str = "localhost"):
        self.command = command
        self.port = port
        self.host = host
        self._process: Optional[asyncio.subprocess.Process] = None
        self._ws: Optional[WebSocketServerProtocol] = None

    async def run(self):
        """Start the bridge."""
        logger.info(f"Starting stdio-to-ws bridge on ws://{self.host}:{self.port}")
        
        try:
            # Start WebSocket server FIRST (so client can connect)
            async with websockets.serve(self._handle_connection, self.host, self.port):
                logger.info(f"WebSocket server running on ws://{self.host}:{self.port}")
                
                # Now spawn the subprocess
                logger.info(f"Spawning subprocess: {' '.join(self.command)}")
                self._process = await asyncio.create_subprocess_exec(
                    *self.command,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                
                logger.info(f"Subprocess spawned with PID {self._process.pid}")
                
                # Log stderr to file (separate from our logging)
                asyncio.create_task(self._log_stderr())
                
                # Keep running until process exits
                await self._process.wait()
        finally:
            # Clean up subprocess when bridge exits
            await self._cleanup()
        
        logger.info("Bridge shutdown")
    
    async def _cleanup(self):
        """Clean up subprocess when bridge exits."""
        if self._process and self._process.returncode is None:
            logger.info(f"Terminating subprocess (PID: {self._process.pid})")
            try:
                self._process.terminate()
                # Wait briefly for graceful shutdown
                try:
                    await asyncio.wait_for(self._process.wait(), timeout=2.0)
                    logger.info("Subprocess terminated gracefully")
                except asyncio.TimeoutError:
                    logger.warning("Subprocess didn't terminate, killing...")
                    self._process.kill()
                    await self._process.wait()
                    logger.info("Subprocess killed")
            except ProcessLookupError:
                logger.info("Subprocess already terminated")
    
    async def _log_stderr(self):
        """Log subprocess stderr to file."""
        if not self._process or not self._process.stderr:
            return
        
        try:
            async for line in self._process.stderr:
                logger.info(f"[stderr] {line.decode('utf-8').rstrip()}")
        except Exception as e:
            logger.error(f"Error reading stderr: {e}")

    async def _handle_connection(self, websocket: WebSocketServerProtocol):
        """Handle WebSocket connection."""
        logger.info("WebSocket client connected")
        self._ws = websocket

        # Create tasks for bidirectional forwarding
        ws_to_stdio = asyncio.create_task(self._forward_ws_to_stdio())
        stdio_to_ws = asyncio.create_task(self._forward_stdio_to_ws())

        try:
            # Wait for either task to complete
            done, pending = await asyncio.wait(
                [ws_to_stdio, stdio_to_ws],
                return_when=asyncio.FIRST_COMPLETED,
            )

            # Cancel pending tasks
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        except Exception as e:
            logger.error(f"Connection error: {e}")
        finally:
            logger.info("WebSocket client disconnected")

    async def _forward_ws_to_stdio(self):
        """Forward WebSocket messages to subprocess stdin."""
        try:
            async for message in self._ws:
                logger.debug(f"WS → stdio: {message[:200]}...")

                # Send to subprocess stdin
                if isinstance(message, str):
                    if not message.endswith("\n"):
                        message += "\n"
                    self._process.stdin.write(message.encode("utf-8"))
                else:
                    if not message.endswith(b"\n"):
                        message += b"\n"
                    self._process.stdin.write(message)

                await self._process.stdin.drain()
        except websockets.exceptions.ConnectionClosed:
            logger.info("WebSocket disconnected")
        except Exception as e:
            logger.error(f"Error forwarding WS to stdio: {e}")

    async def _forward_stdio_to_ws(self):
        """Forward subprocess stdout to WebSocket."""
        try:
            buffer = b""
            chunk_size = 64 * 1024  # 64KB chunks

            while True:
                chunk = await self._process.stdout.read(chunk_size)
                if not chunk:
                    # EOF
                    if buffer:
                        text = buffer.decode("utf-8").rstrip("\n")
                        if text:
                            await self._ws.send(text)
                    break

                buffer += chunk

                # Process complete lines
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    text = line.decode("utf-8")
                    if text:
                        logger.debug(f"stdio → WS: {text[:200]}...")
                        await self._ws.send(text)
        except Exception as e:
            logger.error(f"Error forwarding stdio to WS: {e}")
        finally:
            # Send any remaining buffer
            if buffer:
                try:
                    text = buffer.decode("utf-8").rstrip("\n")
                    if text:
                        await self._ws.send(text)
                except:
                    pass


async def main():
    import argparse

    parser = argparse.ArgumentParser(description="stdio-to-WebSocket bridge")
    parser.add_argument(
        "--port", type=int, default=8765, help="WebSocket port (default: 8765)"
    )
    parser.add_argument(
        "--host", default="localhost", help="WebSocket host (default: localhost)"
    )
    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help="Command to spawn (e.g., 'uv run echo_agent.py') - all remaining args",
    )

    args = parser.parse_args()

    bridge = StdioToWsBridge(
        command=args.command,
        port=args.port,
        host=args.host,
    )

    await bridge.run()


if __name__ == "__main__":
    asyncio.run(main())
