"""HTTP multi-session proof for the refactored AcpAgent.

Connection A (HTTP+SSE): initialize -> new_session -> prompt (plants a fact).
Connection B (WebSocket): initialize -> prompt the SAME session_id with NO
new_session and NO load_session. Server-side, connection B is a brand-new
AcpAgent instance with an empty _sessions dict, so a correct answer proves
the DB-authoritative _resolve_session hydrate path.

Note: B uses WebSocket because the SDK's HTTP+SSE transport gates
session-scoped POSTs on its own per-connection session registry, and a
session/load response carries no sessionId to register there — so over
HTTP+SSE only session/new can establish a session. WS delivers straight to
the agent, which is exactly the agent-side resolution we're proving.
"""

import asyncio

from acp import PROTOCOL_VERSION, connect_to_agent
from acp.http.client import create_http_stream
from acp.ws.client import create_websocket_stream
from acp.schema import ClientCapabilities, Implementation, TextContentBlock

URL = "http://127.0.0.1:2769/"
WS_URL = "ws://127.0.0.1:2769/"
SECRET = "4271"


class RecorderClient:
    """Minimal ACP client: records agent chunks, stubs everything else."""

    def __init__(self, name: str):
        self.name = name
        self.text: list[str] = []
        self.thoughts: list[str] = []
        self.updates: list[str] = []

    def on_connect(self, conn):
        pass

    async def session_update(self, session_id, update, **kwargs):
        kind = getattr(update, "session_update", None)
        self.updates.append(str(kind))
        content = getattr(update, "content", None)
        if content is not None and getattr(content, "type", None) == "text":
            if kind == "agent_message_chunk":
                self.text.append(content.text)
            elif kind == "agent_thought_chunk":
                self.thoughts.append(content.text)

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


async def connect(name: str, transport: str = "http"):
    client = RecorderClient(name)
    if transport == "ws":
        stream = await create_websocket_stream(WS_URL)
    else:
        stream = create_http_stream(URL)
    conn = connect_to_agent(client, stream)
    await conn.initialize(
        protocol_version=PROTOCOL_VERSION,
        client_capabilities=ClientCapabilities(terminal=False),
        client_info=Implementation(name=f"http-test-{name}", version="0.0.0"),
    )
    return client, conn


async def main():
    # --- Connection A: create the session and plant a fact ----------------
    client_a, conn_a = await connect("A")
    new = await conn_a.new_session(cwd="/tmp", mcp_servers=[])
    session_id = new.session_id
    print(f"[A] new session: {session_id}")

    resp_a = await conn_a.prompt(
        session_id=session_id,
        prompt=[
            TextContentBlock(
                type="text",
                text=(
                    f"Remember this number: {SECRET}. Reply with exactly the "
                    "word 'stored' and nothing else. Use no tools."
                ),
            )
        ],
    )
    answer_a = "".join(client_a.text).strip()
    print(f"[A] stop_reason={resp_a.stop_reason} answer={answer_a!r}")
    await conn_a.close()

    # --- Connection B: fresh agent instance, NO new/load_session ----------
    client_b, conn_b = await connect("B", transport="ws")
    resp_b = await conn_b.prompt(
        session_id=session_id,
        prompt=[
            TextContentBlock(
                type="text",
                text=(
                    "What number did I ask you to remember? Reply with exactly "
                    "the number and nothing else. Use no tools."
                ),
            )
        ],
    )
    answer_b = "".join(client_b.text).strip()
    print(f"[B] stop_reason={resp_b.stop_reason} answer={answer_b!r}")
    await conn_b.close()

    # --- Verdict ------------------------------------------------------------
    ok = SECRET in answer_b and resp_b.stop_reason == "end_turn"
    print(f"\nHYDRATION {'OK' if ok else 'FAILED'}: "
          f"connection B answered from a session it never created")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    asyncio.run(main())
