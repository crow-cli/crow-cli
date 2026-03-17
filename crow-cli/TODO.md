# TO DO


## REPLACE ZED AS DAILY DRIVER

- fork ACP extension and make our own. Integrate every different ACP agent in the registry. We can package fnm and uv with crow-cli like "hey install fnm and uv to use crow-cli" as the first step of install lmfao. I can fix the deployment pattern that I've been working on to get into zed but yeah I want to support all distribution mechanisms of acp registry in the crow editor
- work with local development builds of vscodium -> code-server
- work on monoextension/theme for vscodium/code-server (`crow-cli install [desktop|web]`) same thing but for normal browser or electron
- VS Code is basically an extension format for a browser with built-in IDE characteristics, which are of course implemented as extensions
- We are going to implement an open source Trae Solo / Google Antigravity using `crow-cli` as not just the deployment mechanism, but also built around `crow-cli acp` and `crow-cli whateverthefuckIendupcallingtheagentclientlol` as an agent development environment
- We have a lot of this actually well along the way with crow-editor, just need to integrate into a vs code monoextension in a sensible fashion
- We can take advantage of playwright to create what we are looking to create and then extend that whole approach as part of the system we are creating
- Target node/react frontend and python backend as the primary types of architecture we support
- Eschew/direct users away from rust and other C++ pure applications until such a time as we develop full support
- We are not going to be the wild west of coding agent environments/ agent development enviroments (ADE), we're going to represent the state of the art of human out of the loop but on the rail verified programming
- No multiagent swarms, single sequences of verifiable steps to mimic how software is developed and deployed in production environments
- The swarms of agents are going to be doing validation from telemetry of the environments lmfao (but not really we'll figure something out you get it)
- But yeah the time to kill zed is now. Kill zed. Take the reigns and make your editor end to end. You have the technology. You're about to have the time hahahaha.


## `crow-cli` updates
- dig into [`fast-agent`](https://github.com/evalstate/fast-agent) and replicate with extreme prejudice some of that functionality through the agent-client system

- agent-client orchestration <- IN PROGRESS
  - [x] Bridge session/new, session/prompt, session/update between upstream client and downstream agent
  - [x] Handle initialize flow (spawn child agent + bridge, connect via WebSocket)
  - [x] Forward cancellation requests
  - [x] Already using real crow-cli as downstream agent (not echo_agent)
  - [ ] Forward tool execution requests from downstream agent to upstream client
    - **THE PROBLEM**: `_execute_client_method()` just calls raw ACP client methods and returns bare dicts. It doesn't send ACP tool call lifecycle updates.
    - **WHAT'S NEEDED**: When downstream agent calls `conn.create_terminal()`, the AgentClient needs to:
      1. Send `ToolCallStart` to upstream client (Zed) - "starting terminal: ls -la"
      2. Execute the actual client method: `await self._conn.create_terminal(...)`
      3. Send `ToolCallProgress(in_progress)` with `TerminalToolCallContent` for live display
      4. Wait for terminal exit, get output
      5. Send `ToolCallProgress(completed/failed)` with final status
    - **PATTERN TO COPY**: `crow-cli/src/crow_cli/agent/tools.py` has the exact implementations:
      - `execute_acp_terminal()` - full terminal lifecycle with ACP updates
      - `execute_acp_write()` - write with ToolCallStart/Progress/Content
      - `execute_acp_read()` - read with ToolCallStart/Progress/Content
      - `execute_acp_edit()` - edit with diff content
      - `execute_acp_tool()` - generic tools (search, fetch) with content
    - **METHODS TO IMPLEMENT PROPERLY**:
      - `create_terminal` → send ToolCallStart → create_terminal → ToolCallProgress(terminal_id) → wait_for_terminal_exit → terminal_output → ToolCallProgress(completed) → return result
      - `read_text_file` → send ToolCallStart → read_text_file → ToolCallProgress(content) → return content
      - `write_text_file` → send ToolCallStart → write_text_file → ToolCallProgress(diff) → ToolCallProgress(completed) → return result
      - `request_permission` → needs proper handling
    - **END TO END FLOW**:
      ```
      Downstream crow-cli calls conn.create_terminal()
          ↓ JSON-RPC over stdio
      Bridge forwards via WebSocket
          ↓
      AgentClient._handle_updates() receives JSON-RPC request
          ↓
      AgentClient._handle_downstream_request() routes it
          ↓
      AgentClient._execute_client_method() needs to:
          - Send ToolCallStart to Zed (upstream)
          - Call self._conn.create_terminal()
          - Send ToolCallProgress updates
          - Return result to downstream
          ↓
      Zed displays terminal output to user
      ```
  - [ ] Handle error cases: upstream client disconnect, bridge crash, WebSocket failures
  - [ ] Add logging/observability for tool execution flow
  
- slash commands <- TODO
- compaction, compaction, compaction <- IN VALIDATION
- skills, skills, skills <- TO DO
- LOOKS LIKE HOOKS ARE BACK ON THE MENU BOYS!!




# CODE IMPROVEMENTS
- refactor configuration copy over at startup to use crow-cli/src/crow_cli/agent/default
- unit testing <- IN PROGRESS
- integration testing <- TODO
- end to end testing <- DONE
- remove dead code
- replace sqlite with LanceDB for optimal multimodal persistence and vector similarity built in
- put a conversation history tool in the crow-mcp toolkit
- work on playwright integration <- this is an extremely high priority

# BUG FIXES
- adding a folder causes ACP to crash
- ~~when we cancel a session we do NOT want to include any crap in the messages might yield things like this so we need to revisit cancellation handling and think about letting that last token trickle in after all~~

- ~~apparently zed uses resource instead of resource_link now, which is fine by me lol. implemented. still having trouble doing for when there are multiple types of resource in the message~~

# BACKLOG
- doom loop detection
- Fix intermittent error in terminal tool since upgrade The key insight is that synchronous blocking code (like `time.sleep()` in the terminal polling loop) inside an `async def` function will block the entire event loop - which could cause hangs if the MCP transport needs to do I/O simultaneously. The fix would be `asyncio.to_thread()` or making the polling truly async. 





# DONE
- ~~refactor react~~ <- DONE
- ~~Fix system prompt to actually include AGENTS.md, render workspace info, add datetime~~
- ~~Fix prompt_id being hard coded, actually use hash of unrendered~~
- ~~Include @-ed files in the context through /files or whatever~~
- ~~Add tool calls and executions token emission~~
- ~~Use AsyncOpenAI client to enable better `session/cancel` behavior~~
- ~~test `load_session` using local model~~
- ~~Make different providers part of the actual configuration <- use a toml file or something in ~/.crow~~
- ~~Add different models to NewSessionResponse(config_options<- put model choices here)~~
- ~~Revisit config option setting and build without using session.model_identifier~~
