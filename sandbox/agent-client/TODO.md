# Agent-Client TODO

## Wins 🎉

### It works! Bidirectional ACP proxy is functional
- Full stack: Zed ↔ stdio ↔ AgentClient ↔ WebSocket ↔ Bridge ↔ crow-cli (stdio)
- initialize, session/new, session/prompt all pass through correctly
- Agent response chunks (thought, message) stream back upstream to Zed
- Tool call updates stream back upstream
- Client capabilities are properly forwarded: terminal, fs/read_text_file, fs/write_text_file
- Downstream agent requests (`terminal/create`, `fs/read_text_file`, `fs/write_text_file`) get forwarded upstream to the real client
- Results from upstream client get serialized and sent back downstream to the agent

### Fixed bugs
- **JSON-RPC method name mismatch**: Changed from `create_terminal`/`read_text_file` to correct ACP protocol names: `terminal/create`, `terminal/output`, `terminal/wait_for_exit`, `terminal/release`, `terminal/kill`, `fs/read_text_file`, `fs/write_text_file`, `session/request_permission`
- **Pydantic serialization**: `WriteTextFileResponse`, `ReleaseTerminalResponse`, `KillTerminalResponse`, `RequestPermissionResponse` need `_serialize_value()` before JSON serialization
- **Cancellation hang**: When WS connection dies, `_handle_updates` now fails all pending futures so callers don't hang forever
- **Downstream agent**: Changed from old frozen backup binary to `uvx crow-cli acp`
- **Import fix**: `FileSystemCapability` (not `FileSystemCapabilities`) in the sandbox's ACP version

## Known Issues

### Cancellation recovery
After cancel, the WS connection can die with "keepalive ping timeout; no close frame received". The bridge process gets stuck. Cleanup works but the session is dead. Need to either:
- Reconnect/reinitialize after cancel
- Make the bridge more resilient to cancellation
- Kill and respawn the bridge on cancel

### Terminal visibility
Can't see terminal output in the UI when the agent calls terminal tools. The `TerminalToolCallContent` type with `terminalId` is forwarded upstream but Zed doesn't display it since the agent-client doesn't implement the terminal capability fully on the upstream side.

### File write tool errors
The write tool sometimes fails with "Object of type WriteTextFileResponse is not JSON serializable" - this should be fixed by `_serialize_value()` but need to verify.

## Architecture

```
Zed (editor)
  ↑↓ stdio
AgentClient (this project)
  ↑↓ WebSocket
stdio_to_ws.py bridge
  ↑↓ stdio
crow-cli acp (downstream agent)
```

## Key Files
- `agent_client.py` - Main proxy agent implementation
- `stdio_to_ws.py` - Bidirectional bridge: WebSocket ↔ subprocess stdio
- `echo_agent.py` - Simple echo agent for testing (just echoes the prompt back)
