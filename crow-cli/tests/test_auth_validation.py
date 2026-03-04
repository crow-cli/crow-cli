#!/usr/bin/env python3
"""Test auth validation against the crow-cli agent."""

import json
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AuthMethod:
    """Auth method with type inferred from _meta."""

    id: str
    name: str
    type: str | None = None
    description: str | None = None


@dataclass
class AuthCheckResult:
    """Result of auth verification."""

    success: bool
    auth_methods: list[AuthMethod] = field(default_factory=list)
    error: str | None = None
    stderr: str | None = None
    raw_response: dict | None = None


def parse_auth_methods(auth_methods_raw: list[dict]) -> list[AuthMethod]:
    """Parse authMethods from initialize response.

    Type detection priority:
    1. Direct "type" field on the auth method
    2. "_meta" keys: "terminal-auth" -> "terminal", "agent-auth" -> "agent"
    3. Default to "agent" if not specified (per AUTHENTICATION.md)
    """
    auth_methods = []

    for method in auth_methods_raw:
        # 1. Check direct "type" field
        auth_type = method.get("type")

        # 2. Check _meta for terminal-auth or agent-auth
        if not auth_type:
            meta = method.get("_meta", {})
            if isinstance(meta, dict):
                if "terminal-auth" in meta:
                    auth_type = "terminal"
                elif "agent-auth" in meta:
                    auth_type = "agent"

        # 3. Default to "agent" per AUTHENTICATION.md
        if not auth_type:
            auth_type = "agent"

        auth_methods.append(
            AuthMethod(
                id=method.get("id", ""),
                name=method.get("name", ""),
                type=auth_type,
                description=method.get("description"),
            )
        )

    return auth_methods


def validate_auth_methods(auth_methods: list[AuthMethod]) -> tuple[bool, str]:
    """Validate that at least one auth method has type 'agent' or 'terminal'."""
    if not auth_methods:
        return False, "No authMethods in response"

    valid_types = {"agent", "terminal"}
    methods_with_valid_type = [m for m in auth_methods if m.type in valid_types]

    if not methods_with_valid_type:
        types_found = [m.type for m in auth_methods]
        return (
            False,
            f"No auth method with type 'agent' or 'terminal'. Found types: {types_found}",
        )

    return True, f"Found {len(methods_with_valid_type)} valid auth method(s)"


def send_jsonrpc(
    proc: subprocess.Popen, method: str, params: dict, msg_id: int = 1
) -> None:
    """Send a JSON-RPC message to the process (raw JSON, newline-delimited)."""
    request = {
        "jsonrpc": "2.0",
        "id": msg_id,
        "method": method,
        "params": params,
    }
    message = json.dumps(request) + "\n"
    proc.stdin.write(message)
    proc.stdin.flush()


def read_jsonrpc(proc: subprocess.Popen, timeout: float) -> dict | None:
    """Read a JSON-RPC response from the process (raw JSON, newline-delimited)."""
    import select

    ready, _, _ = select.select([proc.stdout], [], [], timeout)
    if not ready:
        return None

    line = proc.stdout.readline()
    if not line:
        return None

    try:
        return json.loads(line)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"ACP spec violation: agent wrote non-JSON to stdout: {line.rstrip()!r}\n"
            f"Per the ACP spec, agents MUST NOT write anything to stdout "
            f"that is not a valid ACP message. "
            f"Diagnostic output should go to stderr."
        ) from e


def run_auth_check(
    cmd: list[str],
    cwd: Path,
    env: dict[str, str] | None = None,
    timeout: float = 60.0,
) -> AuthCheckResult:
    """Verify an agent supports ACP authentication.

    Args:
        cmd: Command to spawn the agent
        cwd: Working directory for the agent process
        env: Environment variables (HOME should be overridden for isolation)
        timeout: Handshake timeout in seconds

    Returns:
        AuthCheckResult with success status and auth methods
    """
    # Build isolated environment
    full_env = os.environ.copy()
    full_env["TERM"] = "dumb"
    if env:
        full_env.update(env)

    # Use a temporary directory as HOME if not specified
    if "HOME" not in (env or {}):
        sandbox_home = tempfile.mkdtemp(prefix="acp-auth-check-")
        full_env["HOME"] = sandbox_home
        # Create the log directory the agent expects
        log_dir = Path(sandbox_home) / ".crow" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

    proc = None
    stderr_output = ""
    response = None
    
    try:
        # Make binary executable if needed
        exe_path = Path(cmd[0])
        if exe_path.exists() and not os.access(exe_path, os.X_OK):
            exe_path.chmod(exe_path.stat().st_mode | 0o755)

        # Start agent process
        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            env=full_env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=0,
        )

        # Send initialize request with capabilities
        send_jsonrpc(
            proc,
            "initialize",
            {
                "protocolVersion": 1,
                "clientInfo": {"name": "ACP Registry Validator", "version": "1.0.0"},
                "clientCapabilities": {
                    "terminal": True,
                    "fs": {
                        "readTextFile": True,
                        "writeTextFile": True,
                    },
                    "_meta": {
                        "terminal_output": True,
                        "terminal-auth": True,
                    },
                },
            },
        )

        # Read response
        response = read_jsonrpc(proc, timeout)

        if response is None:
            # Grab whatever stderr we can
            import select
            if select.select([proc.stderr], [], [], 0.1)[0]:
                stderr_output = proc.stderr.read()
            return AuthCheckResult(
                success=False,
                error=f"Timeout after {timeout}s waiting for initialize response",
                stderr=stderr_output,
            )

        if "error" in response:
            return AuthCheckResult(
                success=False,
                error=f"Agent error: {response['error']}",
                raw_response=response,
            )

        result = response.get("result", {})
        auth_methods_raw = result.get("authMethods", [])

        # Parse auth methods
        auth_methods = parse_auth_methods(auth_methods_raw)

        # Validate
        is_valid, message = validate_auth_methods(auth_methods)

        return AuthCheckResult(
            success=is_valid,
            auth_methods=auth_methods,
            error=None if is_valid else message,
            raw_response=response,
        )

    except Exception as e:
        return AuthCheckResult(
            success=False,
            error=f"Error during auth check: {type(e).__name__}: {e}",
            stderr=stderr_output,
            raw_response=response,
        )
    finally:
        if proc:
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()


def test_auth_validation():
    """Test that crow-cli agent returns valid auth methods."""
    project_path = Path("/home/thomas/src/backup/nid-backup/crow-cli")

    result = run_auth_check(
        cmd=["uv", "--project", str(project_path), "run", "crow-cli", "acp"],
        cwd=project_path,
        timeout=30.0,
    )

    print(f"\n=== Auth Check Result ===")
    print(f"Success: {result.success}")
    print(f"Error: {result.error}")
    
    if result.raw_response:
        print(f"\n=== Raw Response ===")
        print(json.dumps(result.raw_response, indent=2))
    
    if result.stderr:
        print(f"\n=== Stderr (last 2000 chars) ===")
        print(result.stderr[-2000:])
    
    print(f"\nAuth Methods ({len(result.auth_methods)}):")
    for method in result.auth_methods:
        print(f"  - id: {method.id}")
        print(f"    name: {method.name}")
        print(f"    type: {method.type}")
        print(f"    description: {method.description}")
        print()

    assert result.success, f"Auth validation failed: {result.error}"


if __name__ == "__main__":
    test_auth_validation()
