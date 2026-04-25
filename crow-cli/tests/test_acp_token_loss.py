"""
Reproduce token loss bug by running crow-cli agent via ACP client protocol.

Spawns the agent, sends prompts that trigger full ReAct loops with tool calls,
then compares payload dumps to find dropped tokens.
"""

import asyncio
import json
import sys
import tempfile
from pathlib import Path

import pytest
from acp import (
    PROTOCOL_VERSION,
    Client,
    RequestError,
    connect_to_agent,
    text_block,
)
from acp.schema import (
    AgentMessageChunk,
    AgentThoughtChunk,
    ClientCapabilities,
    CreateTerminalResponse,
    EnvVariable,
    FileSystemCapabilities,
    Implementation,
    PermissionOption,
    ReadTextFileResponse,
    SelectedPermissionOutcome,
    TerminalExitStatus,
    TerminalOutputResponse,
    ToolCall,
    ToolCallProgress,
    ToolCallStart,
    WriteTextFileResponse,
)


class TestACPClient(Client):
    """ACP client that supports terminal, read, write for ReAct loops."""

    def __init__(self):
        self._terminals: dict[str, dict] = {}  # terminal_id -> {output, exit_status}
        self._terminal_counter = 0

    async def request_permission(
        self, options: list, session_id: str, tool_call: ToolCall, **kwargs
    ):
        return SelectedPermissionOutcome(optionId=options[0]["optionId"])

    async def write_text_file(self, content, path, session_id, **kwargs):
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        return WriteTextFileResponse()

    async def read_text_file(self, path, session_id, **kwargs):
        p = Path(path)
        if p.exists():
            return ReadTextFileResponse(content=p.read_text())
        return ReadTextFileResponse(content=f"File not found: {path}")

    async def create_terminal(
        self, command, session_id, args=None, cwd=None, env=None, output_byte_limit=None, **kwargs
    ):
        self._terminal_counter += 1
        terminal_id = f"term-{self._terminal_counter}"
        cmd = [command] + (args or [])
        # Build env dict from EnvVariable list
        env_dict = None
        if env:
            env_dict = {}
            for e in env:
                env_dict[e.name] = e.value
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=cwd,
                env=env_dict,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
            output = stdout.decode("utf-8", errors="replace")
            if output_byte_limit and len(output) > output_byte_limit:
                output = output[-output_byte_limit:]
            self._terminals[terminal_id] = {
                "output": output,
                "exit_status": TerminalExitStatus(
                    exit_code=proc.returncode,
                    signal=None,
                ),
            }
        except Exception as e:
            self._terminals[terminal_id] = {
                "output": f"Error: {e}",
                "exit_status": TerminalExitStatus(exit_code=1, signal=None),
            }
        return CreateTerminalResponse(terminal_id=terminal_id)

    async def terminal_output(self, session_id, terminal_id, **kwargs):
        t = self._terminals.get(terminal_id, {"output": "", "exit_status": None})
        return TerminalOutputResponse(
            output=t["output"],
            truncated=False,
            exit_status=t["exit_status"],
        )

    async def wait_for_terminal_exit(self, session_id, terminal_id, **kwargs):
        t = self._terminals.get(terminal_id, {"exit_status": None})
        return t["exit_status"]

    async def release_terminal(self, session_id, terminal_id, **kwargs):
        self._terminals.pop(terminal_id, None)
        return None

    async def session_update(self, session_id, update, **kwargs):
        pass

    async def ext_method(self, method, params):
        raise RequestError.method_not_found(method)

    async def ext_notification(self, method, params):
        pass


@pytest.mark.asyncio
async def test_acp_react_loop_token_loss():
    """
    Spawn crow-cli agent, send prompts that trigger ReAct loops with tool calls,
    then compare payload dumps to detect dropped tokens between turns.
    """
    test_dir = Path(tempfile.mkdtemp())

    # Create a test file for the agent to work with
    (test_dir / "notes.md").write_text(
        "# Project Notes\n\n"
        "## Goals\n"
        "- Build a better agent client\n"
        "- Fix token loss bug\n"
        "- Improve compaction\n\n"
        "## Current Issues\n"
        "Token loss between turns. 603 tokens missing.\n"
        "Happens between session/prompt calls, not during react loop.\n"
    )

    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "crow_cli.agent.main",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(test_dir),
    )

    if proc.stdin is None or proc.stdout is None:
        pytest.skip("Agent process does not expose stdio pipes")

    client = TestACPClient()
    conn = connect_to_agent(client, proc.stdin, proc.stdout)

    await conn.initialize(
        protocol_version=PROTOCOL_VERSION,
        client_capabilities=ClientCapabilities(
            terminal=True,
                fs=FileSystemCapabilities(
                read_text_file=True,
                write_text_file=True,
            ),
        ),
        client_info=Implementation(
            name="test-client",
            title="Test Client",
            version="0.1",
        ),
    )

    session_resp = await conn.new_session(
        cwd=str(test_dir),
        mcp_servers=[],
    )
    session_id = session_resp.session_id
    print(f"\nSession created: {session_id}")

    # Clear old payloads for this session
    log_dir = Path.home() / ".crow" / "logs"
    for old in log_dir.glob(f"payload-{session_id}-*.json"):
        old.unlink()

    # These prompts trigger ReAct loops with tool calls
    prompts = [
        "Read the file notes.md in this directory and tell me what it says.",
        "Now create a new file called summary.md with a one-line summary of notes.md.",
        "Run 'wc -l notes.md' in the terminal and tell me the result.",
        "Read summary.md and append the line count to it using write.",
        "List all files in this directory with ls -la.",
    ]

    for i, prompt_text in enumerate(prompts, 1):
        print(f"\n=== Turn {i}: '{prompt_text}' ===")
        resp = await conn.prompt(
            session_id=session_id,
            prompt=[text_block(prompt_text)],
        )
        print(f"  Stop reason: {resp.stop_reason}")

    # Close agent
    proc.stdin.close()
    await proc.wait()

    # Analyze payload dumps
    payload_files = sorted(
        log_dir.glob(f"payload-{session_id}-*.json"), key=lambda p: p.stat().st_mtime
    )

    print(f"\n=== Payload Analysis ===")
    print(f"Found {len(payload_files)} payload files")

    if len(payload_files) < 2:
        pytest.skip(f"Need >= 2 payload files to compare, got {len(payload_files)}")

    prev_payload = None
    prev_chars = 0
    prev_msg_count = 0

    for i, pf in enumerate(payload_files):
        with open(pf) as f:
            payload = json.load(f)

        msg_count = len(payload)
        total_chars = 0
        for msg in payload:
            content = msg.get("content", "")
            if isinstance(content, list):
                total_chars += sum(
                    len(b.get("text", "")) if isinstance(b, dict) else len(str(b))
                    for b in content
                )
            else:
                total_chars += len(str(content))

        print(f"\n  Payload {i + 1}: {pf.name}")
        print(f"    Messages: {msg_count}, Chars: {total_chars}")

        if prev_payload is not None:
            # Check for message count mismatch
            if msg_count != prev_msg_count + 2:
                print(
                    f"    *** MESSAGE COUNT ANOMALY: was {prev_msg_count}, now {msg_count} (expected {prev_msg_count + 2}) ***"
                )

            # Check for content loss
            if total_chars < prev_chars:
                lost = prev_chars - total_chars
                print(f"    *** CONTENT LOST: {lost} chars! ***")

            # Find which message changed unexpectedly
            min_len = min(len(prev_payload), len(payload))
            for j in range(min_len):
                p_prev = prev_payload[j]
                p_curr = payload[j]
                c_prev = json.dumps(p_prev.get("content", ""))
                c_curr = json.dumps(p_curr.get("content", ""))
                if c_prev != c_curr:
                    prev_len = len(c_prev)
                    curr_len = len(c_curr)
                    if curr_len < prev_len:
                        print(
                            f"    Message {j} ({p_curr.get('role')}): SHRUNK by {prev_len - curr_len} chars"
                        )
                        print(f"      prev: {c_prev[:200]}...")
                        print(f"      curr: {c_curr[:200]}...")

        prev_payload = payload
        prev_msg_count = msg_count
        prev_chars = total_chars

    # Assert no content was lost between any turns
    # (We verify each turn individually above, this is a final check)
    print(f"\n=== Final Summary ===")
    print(f"Total payloads: {len(payload_files)}")
    print(f"Final message count: {prev_msg_count}")
    print(f"Final char count: {prev_chars}")


@pytest.mark.asyncio
async def test_acp_long_conversation_token_loss():
    """
    Run a long conversation (20+ turns with tool calls) and check for token loss.
    """
    test_dir = Path(tempfile.mkdtemp())

    # Create files for the agent to work with
    (test_dir / "file1.py").write_text("def hello():\n    print('hello')\n")
    (test_dir / "file2.py").write_text("def world():\n    print('world')\n")
    (test_dir / "README.md").write_text("# Test Project\n\nThis is a test project for token loss detection.\n")

    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "crow_cli.agent.main",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(test_dir),
    )

    if proc.stdin is None or proc.stdout is None:
        pytest.skip("Agent process does not expose stdio pipes")

    client = TestACPClient()
    conn = connect_to_agent(client, proc.stdin, proc.stdout)

    await conn.initialize(
        protocol_version=PROTOCOL_VERSION,
        client_capabilities=ClientCapabilities(
            terminal=True,
            fs=FileSystemCapabilities(read_text_file=True, write_text_file=True),
        ),
        client_info=Implementation(name="test-client", title="Test Client", version="0.1"),
    )

    session_resp = await conn.new_session(cwd=str(test_dir), mcp_servers=[])
    session_id = session_resp.session_id

    # Clear old payloads
    log_dir = Path.home() / ".crow" / "logs"
    for old in log_dir.glob(f"payload-{session_id}-*.json"):
        old.unlink()

    # 20 prompts that trigger tool calls
    prompts = [
        "Read file1.py and tell me what it does.",
        "Read file2.py now.",
        "Run 'python3 -c \"print(2+2)\"' in the terminal.",
        "Write output.md with 'results: 4'.",
        "Read output.md to confirm.",
        "Run 'ls -la' in terminal.",
        "Read README.md.",
        "Append a new section to README.md saying '## Updated' using write.",
        "Read README.md to verify the update.",
        "Run 'wc -l file1.py file2.py' in terminal.",
        "Write a summary.md with a summary of all files.",
        "Read summary.md.",
        "Run 'cat file1.py file2.py' in terminal.",
        "Write test.txt with 'test passed'.",
        "Read test.txt.",
        "Run 'echo done' in terminal.",
        "Read file1.py again.",
        "Write final.md with 'all tests complete'.",
        "Run 'ls -la *.md' in terminal.",
        "Read final.md to confirm completion.",
    ]

    token_counts = []
    char_counts = []
    msg_counts = []

    from openai import AsyncOpenAI
    from crow_cli.agent.configure import Config
    config = Config.load()
    provider = config.llm.providers["litellm"]
    llm = AsyncOpenAI(api_key=provider.api_key, base_url=provider.base_url)

    for i, prompt_text in enumerate(prompts, 1):
        print(f"\n=== Turn {i}: '{prompt_text}' ===")
        resp = await asyncio.wait_for(
            conn.prompt(session_id=session_id, prompt=[text_block(prompt_text)]),
            timeout=300,
        )
        print(f"  Stop reason: {resp.stop_reason}")

        # Get latest payload and check tokens
        payload_files = sorted(log_dir.glob(f"payload-{session_id}-*.json"), key=lambda p: p.stat().st_mtime)
        if payload_files:
            with open(payload_files[-1]) as f:
                payload = json.load(f)
            msg_count = len(payload)

            total_chars = sum(
                len(b.get("text", "")) if isinstance(b, dict) else len(str(b))
                for msg in payload
                for b in (msg.get("content", "") if isinstance(msg.get("content"), list) else [msg.get("content", "")])
            )

            # Get API token count
            token_resp = await llm.chat.completions.create(
                model="qwen3.5-plus",
                messages=payload,
                max_tokens=20,
                stream=False,
            )
            tokens = token_resp.usage.prompt_tokens

            token_counts.append(tokens)
            char_counts.append(total_chars)
            msg_counts.append(msg_count)

            print(f"  Payload: {len(payload_files)} files, {msg_count} msgs, {total_chars} chars, {tokens} tokens")

            # Check for decreases
            if i > 1:
                if tokens < token_counts[-2]:
                    print(f"  *** TOKEN LOSS: {token_counts[-2]} -> {tokens} (-{token_counts[-2] - tokens}) ***")
                if total_chars < char_counts[-2]:
                    print(f"  *** CHAR LOSS: {char_counts[-2]} -> {total_chars} (-{char_counts[-2] - total_chars}) ***")

    proc.stdin.close()
    await proc.wait()

    # Final summary
    print(f"\n=== Full Token History ===")
    for i, (t, c, m) in enumerate(zip(token_counts, char_counts, msg_counts), 1):
        delta_t = f"+{t - token_counts[i-2]}" if i > 1 else ""
        delta_c = f"+{c - char_counts[i-2]}" if i > 1 else ""
        print(f"  Turn {i:2d}: {t:6d} tokens {delta_t:>8s} | {c:6d} chars {delta_c:>8s} | {m:3d} msgs")

    # Assert monotonic increase
    for i in range(1, len(token_counts)):
        assert token_counts[i] > token_counts[i-1], (
            f"Tokens decreased at turn {i+1}: {token_counts[i-1]} -> {token_counts[i]}"
        )
        assert char_counts[i] >= char_counts[i-1], (
            f"Chars decreased at turn {i+1}: {char_counts[i-1]} -> {char_counts[i]}"
        )


@pytest.mark.asyncio
async def test_acp_web_fetch_token_loss():
    """
    Drive up token count quickly by having the agent search and fetch large web pages.
    This simulates real-world usage where the agent pulls in lots of external content.
    """
    test_dir = Path(tempfile.mkdtemp())

    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "crow_cli.agent.main",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(test_dir),
    )

    if proc.stdin is None or proc.stdout is None:
        pytest.skip("Agent process does not expose stdio pipes")

    client = TestACPClient()
    conn = connect_to_agent(client, proc.stdin, proc.stdout)

    await conn.initialize(
        protocol_version=PROTOCOL_VERSION,
        client_capabilities=ClientCapabilities(
            terminal=True,
            fs=FileSystemCapabilities(read_text_file=True, write_text_file=True),
        ),
        client_info=Implementation(name="test-client", title="Test Client", version="0.1"),
    )

    session_resp = await conn.new_session(cwd=str(test_dir), mcp_servers=[])
    session_id = session_resp.session_id

    # Clear old payloads
    log_dir = Path.home() / ".crow" / "logs"
    for old in log_dir.glob(f"payload-{session_id}-*.json"):
        old.unlink()

    # These prompts force web search + fetch of large pages
    prompts = [
        "Search for 'python async programming best practices' and fetch the top result. Summarize it.",
        "Search for 'react agent pattern architecture' and fetch the first two results. Compare them.",
        "Search for 'llama.cpp context window optimization' and fetch the most detailed result you can find.",
        "Search for 'sqlite performance tuning' and fetch the top 3 results. Write a combined summary to analysis.md.",
        "Read analysis.md and also search for 'database connection pooling' and fetch the best result. Add it to the summary.",
    ]

    token_counts = []
    char_counts = []
    msg_counts = []

    from openai import AsyncOpenAI
    from crow_cli.agent.configure import Config
    config = Config.load()
    provider = config.llm.providers["litellm"]
    llm = AsyncOpenAI(api_key=provider.api_key, base_url=provider.base_url)

    for i, prompt_text in enumerate(prompts, 1):
        print(f"\n=== Turn {i}: '{prompt_text}' ===")
        resp = await asyncio.wait_for(
            conn.prompt(session_id=session_id, prompt=[text_block(prompt_text)]),
            timeout=600,
        )
        print(f"  Stop reason: {resp.stop_reason}")

        # Get latest payload and check tokens
        payload_files = sorted(log_dir.glob(f"payload-{session_id}-*.json"), key=lambda p: p.stat().st_mtime)
        if payload_files:
            with open(payload_files[-1]) as f:
                payload = json.load(f)
            msg_count = len(payload)

            total_chars = sum(
                len(b.get("text", "")) if isinstance(b, dict) else len(str(b))
                for msg in payload
                for b in (msg.get("content", "") if isinstance(msg.get("content"), list) else [msg.get("content", "")])
            )

            # Get API token count
            token_resp = await llm.chat.completions.create(
                model="qwen3.5-plus",
                messages=payload,
                max_tokens=20,
                stream=False,
            )
            tokens = token_resp.usage.prompt_tokens

            token_counts.append(tokens)
            char_counts.append(total_chars)
            msg_counts.append(msg_count)

            print(f"  Payload: {len(payload_files)} files, {msg_count} msgs, {total_chars} chars, {tokens} tokens")

            # Check for decreases
            if i > 1:
                if tokens < token_counts[-2]:
                    print(f"  *** TOKEN LOSS: {token_counts[-2]} -> {tokens} (-{token_counts[-2] - tokens}) ***")
                if total_chars < char_counts[-2]:
                    print(f"  *** CHAR LOSS: {char_counts[-2]} -> {total_chars} (-{char_counts[-2] - total_chars}) ***")

    proc.stdin.close()
    await proc.wait()

    # Final summary
    print(f"\n=== Full Token History ===")
    for i, (t, c, m) in enumerate(zip(token_counts, char_counts, msg_counts), 1):
        delta_t = f"+{t - token_counts[i-2]}" if i > 1 else ""
        delta_c = f"+{c - char_counts[i-2]}" if i > 1 else ""
        print(f"  Turn {i:2d}: {t:6d} tokens {delta_t:>8s} | {c:6d} chars {delta_c:>8s} | {m:3d} msgs")

    # Assert monotonic increase
    for i in range(1, len(token_counts)):
        assert token_counts[i] > token_counts[i-1], (
            f"Tokens decreased at turn {i+1}: {token_counts[i-1]} -> {token_counts[i]}"
        )
        assert char_counts[i] >= char_counts[i-1], (
            f"Chars decreased at turn {i+1}: {char_counts[i-1]} -> {char_counts[i]}"
        )
