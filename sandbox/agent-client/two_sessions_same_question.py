"""Two sessions, same question, prompts fired CONCURRENTLY over one HTTP+SSE
connection: 'what is your session id?' Exercises the per-session lock design
(parallel across sessions, serialized within) and proves no cross-talk."""

import asyncio
import os

from acp import PROTOCOL_VERSION, connect_to_agent
from acp.http.client import create_http_stream
from acp.schema import ClientCapabilities, Implementation, TextContentBlock

URL = "http://127.0.0.1:2769/"
MODEL = os.environ.get("TWO_SESSION_MODEL", "alibaba:qwen3.8-max-preview")
QUESTION = (
    "What is your session id? Reply with exactly the session id and "
    "nothing else. Use no tools."
)


class RecorderClient:
    def __init__(self):
        self.text: dict[str, list[str]] = {}

    def on_connect(self, conn):
        pass

    async def session_update(self, session_id, update, **kwargs):
        if getattr(update, "session_update", None) == "agent_message_chunk":
            content = getattr(update, "content", None)
            if content is not None and getattr(content, "type", None) == "text":
                self.text.setdefault(str(session_id), []).append(content.text)

    async def request_permission(self, *a, **k):
        raise RuntimeError("not expected")

    async def write_text_file(self, *a, **k):
        raise RuntimeError("not expected")

    async def read_text_file(self, *a, **k):
        raise RuntimeError("not expected")

    async def create_terminal(self, *a, **k):
        raise RuntimeError("not expected")

    async def terminal_output(self, *a, **k):
        raise RuntimeError("not expected")

    async def release_terminal(self, *a, **k):
        pass

    async def wait_for_terminal_exit(self, *a, **k):
        pass

    async def kill_terminal(self, *a, **k):
        pass

    async def create_elicitation(self, *a, **k):
        raise RuntimeError("not expected")

    async def complete_elicitation(self, *a, **k):
        pass

    async def ext_method(self, method, params):
        return {}

    async def ext_notification(self, method, params):
        pass


async def main():
    client = RecorderClient()
    conn = connect_to_agent(client, create_http_stream(URL))
    await conn.initialize(
        protocol_version=PROTOCOL_VERSION,
        client_capabilities=ClientCapabilities(terminal=False),
        client_info=Implementation(name="two-session-demo", version="0.0.0"),
    )

    s1 = (await conn.new_session(cwd="/tmp", mcp_servers=[])).session_id
    s2 = (await conn.new_session(cwd="/tmp", mcp_servers=[])).session_id
    print(f"[session 1] created: {s1}")
    print(f"[session 2] created: {s2}")

    # Route both sessions to the chosen model (client-side, per ACP
    # session/set_config_option) instead of the server default.
    for sid in (s1, s2):
        await conn.set_config_option(
            config_id="model", session_id=sid, value=MODEL
        )

    prompt = [TextContentBlock(type="text", text=QUESTION)]
    r1, r2 = await asyncio.gather(
        conn.prompt(session_id=s1, prompt=prompt),
        conn.prompt(session_id=s2, prompt=prompt),
    )

    ans1 = "".join(client.text.get(str(s1), [])).strip()
    ans2 = "".join(client.text.get(str(s2), [])).strip()
    print(f"[session 1] stop_reason={r1.stop_reason} answer={ans1!r}")
    print(f"[session 2] stop_reason={r2.stop_reason} answer={ans2!r}")
    await conn.close()

    ok = (
        s1 != s2
        and s1 in ans1 and s2 in ans2
        and s1 not in ans2 and s2 not in ans1
    )
    print(f"\nVERDICT: {'OK — concurrent sessions, each reported its own id, no cross-talk' if ok else 'MISMATCH'}")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    asyncio.run(main())
