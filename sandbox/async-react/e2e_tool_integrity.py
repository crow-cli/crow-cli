#!/usr/bin/env python3
"""
End-to-end tool call integrity test — runs the actual async react loop,
persists through Session, reloads, and compares what was sent to the API
vs what was stored in the DB.

The entire pipeline: send_request -> process_response -> process_tool_call_inputs
-> add_response_to_messages -> Session.add_assistant_response -> Session.load

Run:
  cd crow-cli/sandbox/async-react && uv --project . run e2e_tool_integrity.py
"""

import asyncio
import hashlib
import json
import logging
import sys
import tempfile
from pathlib import Path

# crow-cli is a dependency
from crow_cli.agent.db import Base, Message, create_database
from crow_cli.agent.db import Session as SessionModel
from crow_cli.agent.prompt import normalize_blocks
from crow_cli.agent.session import Session, get_coolname
from dotenv import load_dotenv
from fastmcp import Client
from openai import AsyncOpenAI

load_dotenv()

MODEL = "qwen3.5-plus"
logger = logging.getLogger("e2e_test")
logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")


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


# ── Exact copies from react.py ──


async def send_request(messages, model, tools, lm, session=None):
    """Same as react.py send_request but without retry/compaction."""
    # Normalize messages exactly as send_request does
    normalized_messages = []
    for msg in messages:
        normalized_msg = dict(msg)
        content = msg.get("content")
        if isinstance(content, list):
            normalized_msg["content"] = normalize_blocks(content)
        normalized_messages.append(normalized_msg)

    response = await lm.chat.completions.create(
        model=model,
        messages=normalized_messages,
        tools=tools,
        stream=True,
    )
    return response, normalized_messages


def process_chunk(chunk, thinking, content, tool_calls):
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
            if index not in tool_calls:
                tool_calls[index] = {"id": "", "function_name": "", "arguments": []}
            if call.id:
                tool_calls[index]["id"] = call.id
            if call.function and call.function.name:
                tool_calls[index]["function_name"] = call.function.name
                new_token = (
                    "tool_call",
                    (call.function.name, call.function.arguments or ""),
                )
            if call.function and call.function.arguments:
                tool_calls[index]["arguments"].append(call.function.arguments)
                if new_token[0] != "tool_call":
                    new_token = ("tool_args", call.function.arguments)

    return thinking, content, tool_calls, new_token


def process_tool_call_inputs(tool_calls):
    tool_call_inputs = []
    for index, tool_call in sorted(tool_calls.items()):
        arguments_str = "".join(tool_call["arguments"])
        try:
            json.loads(arguments_str)
        except json.JSONDecodeError, TypeError, ValueError:
            try:
                if arguments_str.count("{") > arguments_str.count("}"):
                    arguments_str = arguments_str + "}" * (
                        arguments_str.count("{") - arguments_str.count("}")
                    )
                if arguments_str.count("[") > arguments_str.count("]"):
                    arguments_str = arguments_str + "]" * (
                        arguments_str.count("[") - arguments_str.count("]")
                    )
                json.loads(arguments_str)
            except json.JSONDecodeError, TypeError, ValueError:
                arguments_str = "{}"

        tool_call_inputs.append(
            {
                "id": tool_call["id"],
                "type": "function",
                "function": {
                    "name": tool_call["function_name"],
                    "arguments": arguments_str,
                },
            }
        )
    return tool_call_inputs


async def process_response(response, state_accumulator):
    thinking, content, tool_calls = [], [], {}
    final_usage = None
    state_accumulator.update(
        {"thinking": thinking, "content": content, "tool_calls": tool_calls}
    )

    async for chunk in response:
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

    tool_call_inputs = process_tool_call_inputs(tool_calls)
    yield "final", (thinking, content, tool_call_inputs, final_usage)


def add_response_to_messages(
    messages, thinking, content, tool_call_inputs, tool_results
):
    if len(content) > 0 and len(thinking) > 0:
        messages.append(
            {
                "role": "assistant",
                "content": "".join(content),
                "reasoning_content": "".join(thinking),
            }
        )
    elif len(thinking) > 0:
        messages.append({"role": "assistant", "reasoning_content": "".join(thinking)})
    elif len(content) > 0:
        messages.append({"role": "assistant", "content": "".join(content)})
    if len(tool_call_inputs) > 0:
        messages.append({"role": "assistant", "tool_calls": tool_call_inputs})
    if len(tool_results) > 0:
        messages.extend(tool_results)
    return messages


def sha256(obj) -> str:
    return hashlib.sha256(
        json.dumps(obj, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]


def main_sync_check(session, db_uri, turn):
    """Compare in-memory messages vs DB-loaded messages for a specific turn."""
    loaded = Session.load(session.session_id, db_uri=db_uri)

    if len(session.messages) != len(loaded.messages):
        return f"COUNT MISMATCH: in_memory={len(session.messages)} loaded={len(loaded.messages)}"

    mismatches = []
    for i, (mem, db_msg) in enumerate(zip(session.messages, loaded.messages)):
        if mem != db_msg:
            mem_hash = sha256(mem)
            db_hash = sha256(db_msg)
            mismatches.append(
                f"  [{i:03d}] role={mem.get('role')} in_mem={mem_hash} db={db_hash}"
            )

            # Drill into tool_calls
            if "tool_calls" in mem and "tool_calls" in db_msg:
                for j, (mtc, dtc) in enumerate(
                    zip(mem["tool_calls"], db_msg["tool_calls"])
                ):
                    if mtc != dtc:
                        for f in set(mtc.keys()) | set(dtc.keys()):
                            if mtc.get(f) != dtc.get(f):
                                mf = str(mtc.get(f))[:100]
                                df = str(dtc.get(f))[:100]
                                mismatches.append(
                                    f"    tool[{j}].{f}: '{mf}' vs '{df}'"
                                )

    if mismatches:
        return f"Turn {turn}: {len(mismatches)} mismatches\n" + "\n".join(mismatches)
    return None


async def run_e2e_test(max_turns=8):
    """Run the actual react loop with tool calls, persist, and compare."""
    tmpdir = Path(tempfile.mkdtemp(prefix="crow-e2e-"))
    db_path = tmpdir / "test.db"
    db_uri = f"sqlite:///{db_path}"
    create_database(db_uri)

    session_id = get_coolname()
    from sqlalchemy import create_engine as sa_create_engine
    from sqlalchemy.orm import Session as SQLAlchemySession
    engine = sa_create_engine(db_uri)
    db = SQLAlchemySession(engine)
    db.add(
        SessionModel(
            session_id=session_id,
            system_prompt="You are a test assistant. Use tools when helpful.",
            tool_definitions=[],
            request_params={"temperature": 0.2},
            model_identifier=MODEL,
        )
    )
    db.commit()
    db.close()

    session = Session(session_id, db_uri=db_uri, cwd="/tmp")
    session.model_identifier = MODEL
    session.messages = [
        {
            "role": "system",
            "content": "You are a test assistant. Use tools when helpful.",
        }
    ]
    session._save_messages(session.messages)

    mcp_client = setup_mcp_client()
    lm = configure_provider()

    # Prompt designed to trigger tool calls across many turns
    messages = list(session.messages)
    messages.append({
        "role": "user",
        "content": "For each of these topics, use your search tool to search for papers, then use web_fetch to get details from the first result: 1) transformer architecture, 2) attention mechanisms, 3) language models, 4) reinforcement learning, 5) computer vision, 6) graph neural networks, 7) diffusion models, 8) self-supervised learning. Do all 8 searches first before doing fetches.",
    })
    session.add_message(messages[-1])

    turn = 0
    all_issues = []

    async with mcp_client:
        tools = await get_tools(mcp_client)

        while turn < max_turns:
            turn += 1
            print(f"\n{'=' * 50}")
            print(f"Turn {turn} — messages: {len(messages)}")

            response, normalized_payload = await send_request(messages, MODEL, tools, lm)

            state_accumulator = {"thinking": [], "content": [], "tool_calls": {}}
            thinking, content, tool_call_inputs, usage = [], [], [], None

            async for msg_type, token in process_response(response, state_accumulator):
                if msg_type == "final":
                    thinking, content, tool_call_inputs, usage = token

            if not tool_call_inputs:
                messages = add_response_to_messages(messages, thinking, content, [], [])
                old_len = len(session.messages)
                session.add_assistant_response(thinking, content, [], logger, usage)
                print(f"  No tool calls. Session: {len(session.messages)} messages (was {old_len})")
                break

            print(f"  Got {len(tool_call_inputs)} tool call(s)")

            # Execute tools
            tool_results = []
            for tc in tool_call_inputs:
                try:
                    args = json.loads(tc["function"]["arguments"])
                    result = await mcp_client.call_tool(tc["function"]["name"], args)
                    tool_results.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": result.content[0].text,
                    })
                except Exception as e:
                    tool_results.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": f"Error: {e}",
                    })
            old_msg_count = len(messages)
            messages = add_response_to_messages(messages, thinking, content, tool_call_inputs, tool_results)
            print(f"  In-memory: +{len(messages) - old_msg_count} messages (total {len(messages)})")

            # Persist through Session (exact same path as react.py)
            old_session_len = len(session.messages)
            session.add_assistant_response(thinking, content, tool_call_inputs, logger, usage)
            session.add_tool_response(tool_results, logger)
            print(
                f"  Persisted: +{len(session.messages) - old_session_len} messages (total {len(session.messages)})"
            )

            # ── CHECK: in-memory vs DB ──
            issue = main_sync_check(session, db_uri, turn)
            if issue:
                all_issues.append(issue)
                print(f"  ✗ MISMATCH: {issue}")
            else:
                print(f"  ✓ Bit-for-bit parity confirmed")

        # ── Final check: reload entire session ──
        print(f"\n{'=' * 50}")
        print("FINAL INTEGRITY CHECK")
        print(f"{'=' * 50}")
        print(f"In-memory messages: {len(session.messages)}")

        loaded = Session.load(session.session_id, db_uri=db_uri)
        print(f"DB-loaded messages: {len(loaded.messages)}")

        if len(session.messages) != len(loaded.messages):
            all_issues.append(
                f"FINAL COUNT MISMATCH: in_memory={len(session.messages)} loaded={len(loaded.messages)}"
            )
        else:
            for i, (mem, db_msg) in enumerate(zip(session.messages, loaded.messages)):
                if mem != db_msg:
                    all_issues.append(
                        f"  [{i:03d}] role={mem.get('role')} hash_mismatch"
                    )

    # Summary
    print(f"\n{'=' * 50}")
    if all_issues:
        print(f"✗ FOUND {len(all_issues)} INTEGRITY ISSUE(S):")
        for issue in all_issues:
            print(issue)
    else:
        print("✓ ALL TURNS: bit-for-bit parity between in-memory and DB")
    print(f"{'=' * 50}")

    import shutil

    shutil.rmtree(tmpdir, ignore_errors=True)

    return len(all_issues) == 0


if __name__ == "__main__":
    success = asyncio.run(run_e2e_test())
    sys.exit(0 if success else 1)
