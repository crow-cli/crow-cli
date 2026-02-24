"""
Test client that ACTUALLY implements terminal support.

This shows how a real ACP client (like Zed) provides terminals to agents.
The client implements create_terminal, wait_for_exit, etc.
"""
import asyncio
import sys
import os
import subprocess
import uuid
from acp import Client, connect_to_agent
from acp.schema import (
    ClientCapabilities, Implementation, TextContentBlock,
    CreateTerminalResponse, TerminalOutputResponse,
    WaitForTerminalExitResponse, EnvVariable
)


class TerminalClient(Client):
    """Test client that ACTUALLY implements terminal via subprocess"""
    
    def __init__(self):
        super().__init__()
        self.terminals = {}  # terminal_id -> process
        print("[CLIENT] TerminalClient initialized with REAL terminal support")
    
    def on_connect(self, conn):
        print(f"[CLIENT] Connected to agent")
    
    async def session_update(self, session_id: str, update, source: str | None = None):
        """Receive updates from agent"""
        if hasattr(update, 'content'):
            content = update.content
            if hasattr(content, 'text'):
                print(f"\n{content.text}")
    
    async def create_terminal(
        self,
        command: str,
        session_id: str,
        args: list[str] | None = None,
        cwd: str | None = None,
        env: list[EnvVariable] | None = None,
        output_byte_limit: int | None = None,
        **kwargs,
    ) -> CreateTerminalResponse:
        """
        CLIENT implements this - creates actual terminal process.
        
        This is what Zed/VSCode would implement to provide terminals.
        We use subprocess to simulate it.
        """
        print(f"\n[CLIENT] Creating terminal for command: {command}")
        
        # Build full command
        full_cmd = [command]
        if args:
            full_cmd.extend(args)
        
        # Convert env list to dict
        env_dict = os.environ.copy()
        if env:
            for env_var in env:
                env_dict[env_var.name] = env_var.value
        
        # Spawn subprocess as "terminal"
        process = await asyncio.create_subprocess_exec(
            *full_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=cwd or os.getcwd(),
            env=env_dict,
        )
        
        # Generate terminal ID
        terminal_id = f"term_{uuid.uuid4().hex[:8]}"
        
        # Store process
        self.terminals[terminal_id] = {
            'process': process,
            'output': [],
            'output_limit': output_byte_limit or 100000,
            'exited': False,
            'exit_status': None,
        }
        
        print(f"[CLIENT] Terminal {terminal_id} created (PID: {process.pid})")
        
        return CreateTerminalResponse(terminal_id=terminal_id)
    
    async def wait_for_terminal_exit(
        self,
        terminal_id: str,
        session_id: str,
        **kwargs,
    ) -> WaitForTerminalExitResponse:
        """Wait for terminal process to complete"""
        print(f"[CLIENT] Waiting for terminal {terminal_id} to exit...")
        
        if terminal_id not in self.terminals:
            raise ValueError(f"Terminal {terminal_id} not found")
        
        term = self.terminals[terminal_id]
        process = term['process']
        
        # Wait for process to complete
        exit_code = await process.wait()
        
        term['exited'] = True
        term['exit_status'] = exit_code
        
        print(f"[CLIENT] Terminal {terminal_id} exited with code {exit_code}")
        
        return WaitForTerminalExitResponse(
            exit_code=exit_code,
            signal=None
        )
    
    async def terminal_output(
        self,
        terminal_id: str,
        session_id: str,
        **kwargs,
    ) -> TerminalOutputResponse:
        """Get output from terminal"""
        print(f"[CLIENT] Getting output for terminal {terminal_id}")
        
        if terminal_id not in self.terminals:
            raise ValueError(f"Terminal {terminal_id} not found")
        
        term = self.terminals[terminal_id]
        process = term['process']
        
        # Read all output
        output = await process.stdout.read()
        output_text = output.decode('utf-8', errors='replace')
        
        # Check if truncated
        truncated = len(output) > term['output_limit']
        if truncated:
            output_text = output_text[:term['output_limit']]
        
        print(f"[CLIENT] Terminal {terminal_id} output ({len(output_text)} bytes)")
        
        return TerminalOutputResponse(
            output=output_text,
            truncated=truncated,
            exit_status=WaitForTerminalExitResponse(
                exit_code=term['exit_status'],
                signal=None
            ) if term['exited'] else None
        )
    
    async def release_terminal(self, terminal_id: str, session_id: str, **kwargs):
        """Release terminal resources"""
        print(f"[CLIENT] Releasing terminal {terminal_id}")
        
        if terminal_id in self.terminals:
            term = self.terminals[terminal_id]
            process = term['process']
            
            # Kill if still running
            if process.returncode is None:
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    process.kill()
            
            del self.terminals[terminal_id]
        
        return {}
    
    async def kill_terminal(self, terminal_id: str, session_id: str, **kwargs):
        """Kill terminal process"""
        print(f"[CLIENT] Killing terminal {terminal_id}")
        
        if terminal_id in self.terminals:
            term = self.terminals[terminal_id]
            process = term['process']
            
            if process.returncode is None:
                process.kill()
                await process.wait()
        
        return {}
    
    async def read_text_file(self, path: str, session_id: str, **kwargs):
        raise NotImplementedError("File ops not implemented")
    
    async def write_text_file(self, path: str, content: str, session_id: str, **kwargs):
        raise NotImplementedError("File ops not implemented")
    
    async def request_permission(self, permission_request, session_id: str, **kwargs):
        return None
    
    async def ext_method(self, method: str, params: dict, **kwargs):
        raise NotImplementedError(method)
    
    async def ext_notification(self, method: str, params: dict, **kwargs):
        pass


async def test_terminal_demo():
    """Test the terminal demo with REAL terminal support"""
    
    print("\n" + "="*60)
    print("TESTING: Real ACP Terminal Implementation")
    print("="*60 + "\n")
    
    # Create client with REAL terminal support
    client = TerminalClient()
    client_caps = ClientCapabilities(terminal=True)
    
    # Spawn agent
    agent_path = "terminal_demo.py"
    print(f"[TEST] Spawning agent: {agent_path}\n")
    
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-u", agent_path,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
    )
    
    if proc.stdin is None or proc.stdout is None:
        print("[ERROR] Agent process does not expose stdio pipes")
        return
    
    # Connect to agent
    conn = connect_to_agent(client, proc.stdin, proc.stdout)
    
    print("[TEST] Connected! Initializing...\n")
    
    # Initialize
    init_response = await conn.initialize(
        protocol_version=1,
        client_capabilities=client_caps,
        client_info=Implementation(
            name="terminal_client",
            version="0.1.0"
        )
    )
    print(f"[TEST] Agent initialized\n")
    
    # Create session
    session_response = await conn.new_session(cwd="/tmp", mcp_servers=[])
    session_id = session_response.session_id
    print(f"[TEST] Created session: {session_id}\n")
    
    # Send prompt that triggers terminal use
    print("[TEST] Sending prompt: 'test terminal'\n")
    print("="*60 + "\n")
    
    prompt = [TextContentBlock(type="text", text="test terminal")]
    response = await conn.prompt(prompt=prompt, session_id=session_id)
    
    print("\n" + "="*60)
    print(f"[TEST] Prompt complete: {response.stop_reason}")
    
    # Cleanup
    proc.terminate()
    await proc.wait()


if __name__ == "__main__":
    asyncio.run(test_terminal_demo())
