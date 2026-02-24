"""
Test client to probe ACP agent capabilities.

This creates a minimal ACP client that:
1. Reports terminal support
2. Connects to an agent (spawns it as subprocess)
3. Sends a prompt
4. Displays the response
"""
import asyncio
import sys
from acp import Client, connect_to_agent
from acp.schema import ClientCapabilities, Implementation, TextContentBlock


class TestClient(Client):
    """Minimal test client that reports terminal support"""
    
    def __init__(self):
        super().__init__()
        print("[CLIENT] TestClient initialized")
    
    def on_connect(self, conn):
        """Called when connected to agent"""
        print(f"[CLIENT] Connected to agent, conn type: {type(conn)}")
    
    # Implement required abstract methods with dummy implementations
    
    async def session_update(self, session_id: str, update, source: str | None = None):
        """Receive updates from agent"""
        print(f"[CLIENT] Received update from agent (source={source}):")
        
        # Try to print the content
        if hasattr(update, 'content'):
            content = update.content
            if hasattr(content, 'text'):
                print(f"[CLIENT] Agent says: {content.text}")
            else:
                print(f"[CLIENT] Content: {content}")
        else:
            print(f"[CLIENT] Update: {update}")
    
    async def create_terminal(self, command: str, session_id: str, **kwargs):
        """Client supports terminals - this is what we're testing!"""
        print(f"[CLIENT] create_terminal called with command={command}")
        # We don't actually implement it, just prove the method exists
        raise NotImplementedError("Test client doesn't actually create terminals")
    
    async def kill_terminal(self, terminal_id: str, session_id: str, **kwargs):
        print(f"[CLIENT] kill_terminal called")
        raise NotImplementedError("Test client doesn't actually kill terminals")
    
    async def release_terminal(self, terminal_id: str, session_id: str, **kwargs):
        print(f"[CLIENT] release_terminal called")
        raise NotImplementedError("Test client doesn't actually release terminals")
    
    async def terminal_output(self, terminal_id: str, session_id: str, **kwargs):
        print(f"[CLIENT] terminal_output called")
        raise NotImplementedError("Test client doesn't actually get terminal output")
    
    async def wait_for_terminal_exit(self, terminal_id: str, session_id: str, **kwargs):
        print(f"[CLIENT] wait_for_terminal_exit called")
        raise NotImplementedError("Test client doesn't actually wait for terminal exit")
    
    async def read_text_file(self, path: str, session_id: str, **kwargs):
        print(f"[CLIENT] read_text_file called")
        raise NotImplementedError("Test client doesn't actually read files")
    
    async def write_text_file(self, path: str, content: str, session_id: str, **kwargs):
        print(f"[CLIENT] write_text_file called")
        raise NotImplementedError("Test client doesn't actually write files")
    
    async def request_permission(self, permission_request, session_id: str, **kwargs):
        print(f"[CLIENT] request_permission called")
        return None
    
    async def ext_method(self, method: str, params: dict, **kwargs):
        print(f"[CLIENT] ext_method called: {method}")
        return None
    
    async def ext_notification(self, method: str, params: dict, **kwargs):
        print(f"[CLIENT] ext_notification: {method}")


async def test_agent_with_client():
    """Test the agent with a client that supports terminals"""
    
    print("\n" + "="*60)
    print("TESTING: Agent receives client capabilities")
    print("="*60 + "\n")
    
    # Create test client with terminal support
    client = TestClient()
    
    # Specify that this client supports terminals
    client_caps = ClientCapabilities(terminal=True)
    
    print(f"[TEST] Client capabilities: {client_caps.model_dump()}")
    print(f"[TEST] Client has terminal support: {client_caps.terminal}")
    
    # Spawn the agent as a subprocess
    agent_path = "fire_up_echo.py"
    print(f"\n[TEST] Spawning agent: {agent_path}\n")
    
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-u", agent_path,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
    )
    
    if proc.stdin is None or proc.stdout is None:
        print("[ERROR] Agent process does not expose stdio pipes")
        return
    
    # Connect to the agent
    conn = connect_to_agent(client, proc.stdin, proc.stdout)
    
    print("[TEST] Connected! Initializing...\n")
    
    # Initialize the agent
    init_response = await conn.initialize(
        protocol_version=1,
        client_capabilities=client_caps,
        client_info=Implementation(
            name="test_client",
            version="0.1.0"
        )
    )
    print(f"[TEST] Agent initialized: {init_response}")
    
    # Create a session
    session_response = await conn.new_session(cwd="/tmp", mcp_servers=[])
    session_id = session_response.session_id
    print(f"[TEST] Created session: {session_id}\n")
    
    # Send a test prompt
    print("[TEST] Sending prompt: 'Hello, what capabilities do you have?'\n")
    
    prompt = [TextContentBlock(type="text", text="Hello, what capabilities do you have?")]
    response = await conn.prompt(prompt=prompt, session_id=session_id)
    
    print(f"\n[TEST] Prompt complete: {response}")
    print(f"[TEST] Stop reason: {response.stop_reason}")
    
    # Cleanup
    proc.terminate()
    await proc.wait()


if __name__ == "__main__":
    asyncio.run(test_agent_with_client())
