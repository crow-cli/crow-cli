#!/usr/bin/env python3
"""
Bit-for-bit persistence integrity test.

Dumps every message to individual JSONL files on disk,
then reloads and compares against in-memory state.

Usage:
    cd crow-cli/sandbox/async-react && uv --project run persistence_integrity_test.py
    cd crow-cli/sandbox/async-react && uv --project run persistence_integrity_test.py --test-cancel
"""

import asyncio
import hashlib
import json
import os
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

from dotenv import load_dotenv
from fastmcp import Client
from openai import AsyncOpenAI

load_dotenv()

MODEL = "qwen3.5-plus"
DELAY = 10.0  # seconds before cancellation fires


class MessageDump:
    """
    Filesystem message persistence using one JSONL file per message.
    Files named {index:04d}-{session_id}.jsonl for natural sort order.
    """

    def __init__(self, session_id: str, dump_dir: str | Path | None = None):
        self.session_id = session_id
        if dump_dir is None:
            dump_dir = Path(tempfile.mkdtemp(prefix="crow-dump-"))
        self.dump_dir = Path(dump_dir)
        self.dump_dir.mkdir(parents=True, exist_ok=True)

    def _filepath(self, index: int) -> Path:
        return self.dump_dir / f"{index:04d}-{self.session_id}.jsonl"

    def save(self, index: int, msg: dict):
        """Write one message as a single-line JSONL file."""
        fp = self._filepath(index)
        with open(fp, "w", encoding="utf-8") as f:
            f.write(json.dumps(msg, ensure_ascii=False) + "\n")

    def load_all(self) -> list[dict]:
        """Read all JSONL files back in sorted order."""
        files = sorted(self.dump_dir.glob(f"*-{self.session_id}.jsonl"))
        messages = []
        for fp in files:
            with open(fp, "r", encoding="utf-8") as f:
                line = f.readline()
                messages.append(json.loads(line))
        return messages

    def cleanup(self):
        shutil.rmtree(self.dump_dir, ignore_errors=True)


def sha256(obj: object) -> str:
    """Deterministic hash of any JSON-serializable object."""
    return hashlib.sha256(
        json.dumps(obj, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:12]


def compare_messages(in_memory: list[dict], from_disk: list[dict]) -> list[str]:
    """
    Compare in-memory messages vs disk-loaded messages.
    Returns list of discrepancy descriptions (empty = perfect parity).
    """
    issues = []

    if len(in_memory) != len(from_disk):
        issues.append(
            f"COUNT MISMATCH: in_memory={len(in_memory)}, disk={len(from_disk)}"
        )

    max_len = max(len(in_memory), len(from_disk))
    for i in range(max_len):
        if i >= len(in_memory):
            issues.append(f"  [{i:04d}] MISSING from in-memory (only on disk)")
            continue
        if i >= len(from_disk):
            issues.append(f"  [{i:04d}] MISSING from disk (only in-memory)")
            continue

        mem = in_memory[i]
        dsk = from_disk[i]

        mem_hash = sha256(mem)
        dsk_hash = sha256(dsk)

        if mem_hash != dsk_hash:
            # Find the specific field that differs
            all_keys = set(mem.keys()) | set(dsk.keys())
            field_issues = []
            for key in sorted(all_keys):
                mem_val = mem.get(key)
                dsk_val = dsk.get(key)
                if mem_val != dsk_val:
                    mem_str = str(mem_val) if mem_val is not None else "<MISSING>"
                    dsk_str = str(dsk_val) if dsk_val is not None else "<MISSING>"
                    # Character-level diff for strings
                    if isinstance(mem_val, str) and isinstance(dsk_val, str):
                        mem_bytes = mem_val.encode("utf-8")
                        dsk_bytes = dsk_val.encode("utf-8")
                        field_issues.append(
                            f"    [{key}] in_mem={len(mem_bytes)}B sha={sha256(mem_val)[:8]} "
                            f"disk={len(dsk_bytes)}B sha={sha256(dsk_val)[:8]}"
                        )
                        if len(mem_bytes) != len(dsk_bytes):
                            field_issues.append(
                                f"      BYTE DIFF: in_memory={len(mem_bytes)}, disk={len(dsk_bytes)} "
                                f"(delta={len(dsk_bytes) - len(mem_bytes)})"
                            )
                    else:
                        field_issues.append(f"    [{key}] VALUES DIFFER")

            issues.append(
                f"  [{i:04d}] role={mem.get('role', '?')}: {len(field_issues)} field(s) differ\n"
                + "\n".join(field_issues)
            )

    return issues


# ── LLM plumbing (same as streaming_async_react_with_cancellation.py) ──


def configure_provider():
    return AsyncOpenAI(
        api_key="EMPTY",
        base_url="http://localhost:4000/v1",
    )


def setup_mcp_client():
    config = {
        "mcpServers": {
            "crow-mcp": {
                "transport": "stdio",
                "command": "uvx",
                "args": ["crow-mcp"],
            }
        }
    }
    return Client(config)


async def get_tools(mcp_client):
    mcp_tools = await mcp_client.list_tools()
    tools = [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.inputSchema,
            },
        }
        for tool in mcp_tools
    ]
    return tools


async def send_request(messages, model, tools, lm):
    try:
        response = await lm.chat.completions.create(
            model=model,
            messages=messages,
            tools=tools,
            stream=True,
        )
        return response
    except Exception as e:
        traceback.print_exc()
        raise ValueError(f"Error sending request: {e}")


def process_chunk(
    chunk,
    thinking: list[str],
    content: list[str],
    tool_calls: dict,
) -> tuple[list[str], list[str], dict, tuple[str | None, Any]]:
    """
    Process a single streaming chunk.

    Matches production crow_cli/agent/react.py process_chunk exactly.
    """
    # Final chunk may have usage but no choices
    if not chunk.choices or len(chunk.choices) == 0:
        return thinking, content, tool_calls, (None, None)

    delta = chunk.choices[0].delta
    new_token = (None, None)

    if not delta.tool_calls:
        reasoning_chunk = getattr(delta, "reasoning_content", None)
        if reasoning_chunk:
            thinking.append(reasoning_chunk)
            new_token = ("thinking", reasoning_chunk)
        else:
            verbal_chunk = delta.content
            if verbal_chunk:
                content.append(verbal_chunk)
                new_token = ("content", verbal_chunk)
    else:
        for call in delta.tool_calls:
            index = call.index

            # Initialize the dictionary for this index if it doesn't exist
            if index not in tool_calls:
                tool_calls[index] = {"id": "", "function_name": "", "arguments": []}

            # Update fields if they are present in this delta
            if call.id:
                tool_calls[index]["id"] = call.id
            if call.function and call.function.name:
                tool_calls[index]["function_name"] = call.function.name
                new_token = (
                    "tool_call",
                    (call.function.name, call.function.arguments or ""),
                )

            if call.function and call.function.arguments:
                arg_fragment = call.function.arguments
                tool_calls[index]["arguments"].append(arg_fragment)
                # Only yield args if we didn't just yield the initial tool_call token above
                if new_token[0] != "tool_call":
                    new_token = ("tool_args", arg_fragment)

    return thinking, content, tool_calls, new_token


def process_tool_call_inputs(tool_calls: dict):
    """
    Process tool call inputs into OpenAI format.

    Matches production crow_cli/agent/react.py process_tool_call_inputs.
    """
    tool_call_inputs = []
    repaired_flags = []
    for index, tool_call in sorted(tool_calls.items()):
        arguments_str = "".join(tool_call["arguments"])
        was_repaired = False

        # Validate and repair JSON if needed
        try:
            json.loads(arguments_str)
        except (json.JSONDecodeError, TypeError, ValueError):
            was_repaired = True
            try:
                # Try adding closing braces/brackets if missing
                if arguments_str.count("{") > arguments_str.count("}"):
                    arguments_str = arguments_str + "}" * (
                        arguments_str.count("{") - arguments_str.count("}")
                    )
                if arguments_str.count("[") > arguments_str.count("]"):
                    arguments_str = arguments_str + "]" * (
                        arguments_str.count("[") - arguments_str.count("]")
                    )
                # Validate again after repair attempt
                json.loads(arguments_str)
            except (json.JSONDecodeError, TypeError, ValueError):
                # Still invalid, use empty object as fallback
                arguments_str = "{}"

        tool_call_inputs.append(
            dict(
                id=tool_call["id"],
                type="function",
                function=dict(
                    name=tool_call["function_name"],
                    arguments=arguments_str,
                ),
            )
        )
        repaired_flags.append(was_repaired)
    return tool_call_inputs, repaired_flags


async def process_response(response, state_accumulator: dict):
    """
    Process streaming response from LLM.

    Matches production crow_cli/agent/react.py process_response.
    """
    thinking = state_accumulator["thinking"]
    content = state_accumulator["content"]
    tool_calls = state_accumulator["tool_calls"]
    final_usage = None

    async for chunk in response:
        # Check for usage in chunk
        if hasattr(chunk, "usage") and chunk.usage is not None:
            final_usage = {
                "prompt_tokens": getattr(chunk.usage, "prompt_tokens", None),
                "completion_tokens": getattr(chunk.usage, "completion_tokens", None),
                "total_tokens": getattr(chunk.usage, "total_tokens", None),
            }

        thinking, content, tool_calls, new_token = process_chunk(
            chunk, thinking, content, tool_calls
        )
        state_accumulator["thinking"] = thinking
        state_accumulator["content"] = content
        state_accumulator["tool_calls"] = tool_calls
        msg_type, token = new_token
        if msg_type:
            yield msg_type, token

    # Yield final result
    tool_call_inputs, _ = process_tool_call_inputs(tool_calls)
    yield "final", (thinking, content, tool_call_inputs, final_usage)


async def execute_tool_calls(mcp_client, tool_call_inputs, verbose=True):
    tool_results = []
    for tool_call in tool_call_inputs:
        try:
            arg_dict = json.loads(tool_call["function"]["arguments"])
            result = await mcp_client.call_tool(
                tool_call["function"]["name"],
                arg_dict,
            )
            tool_results.append(
                dict(
                    role="tool",
                    tool_call_id=tool_call["id"],
                    content=result.content[0].text,
                )
            )
            if verbose:
                print()
                print("TOOL RESULT:")
                print(f"{tool_call['function']['name']}: ")
                print(f"{result.content[0].text}")
        except Exception as e:
            tool_results.append(
                dict(
                    role="tool",
                    tool_call_id=tool_call["id"],
                    content=f"Error: {str(e)}",
                )
            )
    return tool_results


def add_response_to_messages(
    messages, thinking, content, tool_call_inputs, tool_results
):
    if len(content) > 0 and len(thinking) > 0:
        messages.append(
            dict(
                role="assistant",
                content="".join(content),
                reasoning_content="".join(thinking),
            )
        )
    elif len(thinking) > 0:
        messages.append(dict(role="assistant", reasoning_content="".join(thinking)))
    elif len(content) > 0:
        messages.append(dict(role="assistant", content="".join(content)))
    if len(tool_call_inputs) > 0:
        messages.append(dict(role="assistant", tool_calls=tool_call_inputs))
    if len(tool_results) > 0:
        messages.extend(tool_results)
    return messages


async def react_loop(
    messages,
    mcp_client,
    lm,
    model,
    tools,
    message_dump: MessageDump,
    cancel_event: asyncio.Event = None,
    on_cancel: callable = None,
    max_turns=50000,
):
    """
    React loop with filesystem persistence on every message add.
    Matches production crow_cli/agent/react.py react_loop pattern.
    """
    msg_index = len(messages)

    # Dump initial messages
    for i, msg in enumerate(messages):
        message_dump.save(i, msg)

    for turn in range(max_turns):
        response = await send_request(messages, model, tools, lm)

        state_accumulator = {"thinking": [], "content": [], "tool_calls": {}}

        gen = process_response(response, state_accumulator)
        thinking, content, tool_call_inputs, usage = [], [], [], None

        async for msg_type, token in gen:
            if msg_type == "final":
                thinking, content, tool_call_inputs, usage = token
            else:
                if cancel_event and cancel_event.is_set():
                    print(f"\n[Cancelled mid-stream]")
                    if on_cancel:
                        on_cancel(
                            state_accumulator["thinking"],
                            state_accumulator["content"],
                            [],  # No tool calls on cancel
                            [],
                        )
                    return

                yield {"type": msg_type, "token": token}

        if cancel_event and cancel_event.is_set():
            print(f"\n[Cancelled before tool execution]")
            if on_cancel:
                on_cancel(thinking, content, [], [])
            return

        if not tool_call_inputs:
            messages = add_response_to_messages(messages, thinking, content, [], [])
            # Persist final assistant message
            message_dump.save(msg_index, messages[-1])
            msg_index += 1
            yield {"type": "final_history", "messages": messages}
            return

        tool_results = await execute_tool_calls(
            mcp_client, tool_call_inputs, verbose=False
        )

        if cancel_event and cancel_event.is_set():
            print(f"\n[Cancelled after tool execution]")
            if on_cancel:
                on_cancel(thinking, content, tool_call_inputs, tool_results)
            return

        old_len = len(messages)
        messages = add_response_to_messages(
            messages, thinking, content, tool_call_inputs, tool_results
        )
        # Persist all new messages from this turn
        for i in range(old_len, len(messages)):
            message_dump.save(msg_index, messages[i])
            msg_index += 1


async def run_integrity_test(cancel: bool = False):
    """Run the full integrity test with real LLM calls."""
    session_id = f"integrity-test-{os.urandom(4).hex()}"
    dump_dir = Path(f"/tmp/crow-integrity-{session_id}")
    dump_dir.mkdir(parents=True, exist_ok=True)

    message_dump = MessageDump(session_id, dump_dir)

    mcp_client = setup_mcp_client()
    lm = configure_provider()

    if cancel:
        messages = [
            dict(role="system", content="You are a helpful assistant named Crow."),
            dict(
                role="user",
                content="Tell me a long story about a robot learning to paint. Include at least 5 paragraphs.",
            ),
        ]
    else:
        messages = [
            dict(role="system", content="You are a helpful assistant named Crow."),
            dict(
                role="user",
                content="search for machine learning papers with your search tool",
            ),
        ]

    cancel_event = asyncio.Event() if cancel else None
    partial_state = {"messages": []}

    def on_cancel(thinking, content, tool_call_inputs, tool_results):
        partial_state["messages"] = add_response_to_messages(
            messages.copy(), thinking, content, tool_call_inputs, tool_results
        )

    if cancel:

        async def cancel_after_delay():
            await asyncio.sleep(DELAY)
            print("\n\n*** SENDING CANCEL ***\n")
            cancel_event.set()

        asyncio.create_task(cancel_after_delay())

    final_history = []
    error_occurred = False
    async with mcp_client:
        tools = await get_tools(mcp_client)
        try:
            async for chunk in react_loop(
                messages,
                mcp_client,
                lm,
                MODEL,
                tools,
                message_dump,
                cancel_event=cancel_event,
                on_cancel=on_cancel,
            ):
                if chunk["type"] == "content":
                    print(chunk["token"], end="", flush=True)
                elif chunk["type"] == "thinking":
                    print(f"\n[Thinking]: {chunk['token']}", end="", flush=True)
                elif chunk["type"] == "tool_call":
                    name, first_arg = chunk["token"]
                    print(f"\n[Tool Call]: {name}({first_arg}", end="", flush=True)
                elif chunk["type"] == "tool_args":
                    print(chunk["token"], end="", flush=True)
                elif chunk["type"] == "final_history":
                    final_history = chunk["messages"]
        except Exception as e:
            print(f"\n[Error during loop: {e}]")
            error_occurred = True

    # Use partial state if cancelled or errored
    target_messages = final_history or partial_state["messages"] or messages

    print("\n\n" + "=" * 60)
    print("PERSISTENCE INTEGRITY CHECK")
    print("=" * 60)
    print(f"Session: {session_id}")
    print(f"Dump dir: {dump_dir}")
    print(f"In-memory messages: {len(target_messages)}")

    # Load from disk
    disk_messages = message_dump.load_all()
    print(f"Disk messages: {len(disk_messages)}")

    # Compare
    issues = compare_messages(target_messages, disk_messages)

    if not issues:
        print("\n✓ BIT-FOR-BIT PARITY CONFIRMED")
        print(f"  {len(target_messages)} messages match perfectly")

        # Show file listing
        files = sorted(dump_dir.glob(f"*-{session_id}.jsonl"))
        print(f"\nDump files ({len(files)} total):")
        for fp in files:
            with open(fp, "r") as f:
                line = f.readline()
                msg = json.loads(line)
                role = msg.get("role", "?")
                content_preview = ""
                if "content" in msg:
                    c = msg["content"]
                    content_preview = f" content={len(str(c))}B"
                if "tool_calls" in msg:
                    content_preview += f" tool_calls={len(msg['tool_calls'])}"
                if "tool_call_id" in msg:
                    content_preview += f" tool_id={msg['tool_call_id'][:12]}..."
                if "reasoning_content" in msg:
                    content_preview += (
                        f" reasoning={len(str(msg['reasoning_content']))}B"
                    )
                print(f"  {fp.name}: role={role}{content_preview}")
    else:
        print(f"\n✗ FOUND {len(issues)} DISCREPANCY(IES):")
        for issue in issues:
            print(issue)

    print(f"\nDump preserved at: {dump_dir}")
    print("To inspect: ls -la", dump_dir)

    return len(issues) == 0


if __name__ == "__main__":
    cancel_mode = "--test-cancel" in sys.argv

    if cancel_mode:
        print("Running integrity test WITH cancellation...")
    else:
        print("Running integrity test (normal mode)...")

    success = asyncio.run(run_integrity_test(cancel=cancel_mode))
    sys.exit(0 if success else 1)
