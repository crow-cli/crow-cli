"""
Example: Running code in an isolated Jupyter kernel programmatically.

This demonstrates how crow can use jupyter_client to:
1. Spin up a kernel pointing at any Python executable
2. Execute code with persistent state
3. Capture stdout, stderr, and return values
4. Handle shell commands separately via subprocess
"""

import subprocess
import time

from jupyter_client import KernelManager


class CrowKernel:
    """A simple wrapper around jupyter_client for crow's IPython cell tool."""

    def __init__(self, python_path: str | None = None):
        self.km = KernelManager()

        # Point at custom python if specified
        if python_path:
            self.km.kernel_spec.argv[0] = python_path

        self.km.start_kernel()
        self.client = self.km.client()
        self.client.start_channels()
        time.sleep(2)  # wait_for_ready() hangs, just sleep

    def execute(self, code: str) -> str:
        """Execute code and return human-readable output."""

        # Shell commands go through subprocess
        if code.strip().startswith("!"):
            return self._run_shell(code.strip()[1:])

        # Python goes through kernel
        return self._run_python(code)

    def _run_shell(self, cmd: str) -> str:
        """Run shell command via subprocess."""
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

        output = []
        if result.stdout:
            output.append(result.stdout.rstrip())
        if result.stderr:
            output.append(result.stderr.rstrip())
        if result.returncode != 0:
            output.append(f"[exit code: {result.returncode}]")

        return "\n".join(output) if output else "[ok]"

    def _run_python(self, code: str) -> str:
        """Run Python code in the kernel."""
        self.client.execute(code)
        reply = self.client.get_shell_msg(timeout=30)

        stdout = []
        stderr = []
        result = None
        error = None

        # Drain iopub messages
        while True:
            try:
                msg = self.client.get_iopub_msg(timeout=2)
                msg_type = msg["msg_type"]
                content = msg["content"]

                if msg_type == "stream":
                    if content["name"] == "stdout":
                        stdout.append(content["text"])
                    else:
                        stderr.append(content["text"])
                elif msg_type == "execute_result":
                    result = content["data"].get("text/plain")
                elif msg_type == "error":
                    error = content
                elif msg_type == "status" and content["execution_state"] == "idle":
                    break
            except:
                break

        return self._format_output(
            success=reply["content"]["status"] == "ok",
            stdout="".join(stdout),
            stderr="".join(stderr),
            result=result,
            error=error,
        )

    def _format_output(
        self,
        success: bool,
        stdout: str,
        stderr: str,
        result: str | None,
        error: dict | None,
    ) -> str:
        """Format output like a human would see in a REPL."""

        # Error first - that's what matters when shit breaks
        if error:
            # Strip ANSI codes for cleaner output (optional, keep if you want color)
            import re

            traceback_lines = [
                re.sub(r"\x1b\[[0-9;]*m", "", line) for line in error["traceback"]
            ]
            return "\n".join(traceback_lines)

        output = []

        # Stdout - what was printed
        if stdout:
            output.append(stdout.rstrip())

        # Stderr - warnings, logs, etc.
        if stderr:
            output.append(stderr.rstrip())

        # Result - expression return value (like REPL shows Out[n])
        if result is not None:
            output.append(result)

        return "\n".join(output)

    def shutdown(self):
        """Shutdown the kernel."""
        self.km.shutdown_kernel(now=True)


def main():
    import os

    # Use test-venv if it exists, otherwise default
    # test_venv = os.path.join(os.path.dirname(__file__), "test-venv", "bin", "python")
    test_venv = "/Users/thomas.wood/src/thomas-wood-notes/test-kernel/.venv/bin/python3"

    if os.path.exists(test_venv):
        print(f"Using test venv: {test_venv}")
        kernel = CrowKernel(python_path=test_venv)
    else:
        print("Using default kernel")
        kernel = CrowKernel()

    tests = [
        "x = 42",
        "print(f'x is {x}')",
        "x * 2",
        "y = x + 100; y",
        "print('calculating...'); y * 2",
        "!echo hello from shell",
        "!exit 1",
        "import sys; sys.executable",
        """
def greet(name):
    return f"hello, {name}!"

greet("crow")
""",
        "1/0",
    ]

    for code in tests:
        print(f"\n{'=' * 50}")
        # Show code with >>> prefix for each line
        for line in code.strip().split("\n"):
            print(f">>> {line}")
        print(kernel.execute(code))

    print(f"\n{'=' * 50}")
    print("Shutting down...")
    kernel.shutdown()
    print("Done!")


if __name__ == "__main__":
    main()
