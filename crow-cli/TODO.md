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
- So I need to take control of my actual IDE and that means using vscodium and code-server pipelines.

Also I'm using code-server though code.advanced-eschatonics.com and honestly I just need to get the monoextension/theme working and plug this into the exact same slot it's using now and I'll be in business. Make a bunch of k8s files and figure out how to make the whole thing distributed in the cloud for different users and put out my shingle for a place for people to host their projects AND work on them. Get into being an LLM provider on top of building crow-cli. This is why the VCs are reaching out to me.

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
  - We really do need some kind of hooks where you can say "okay you can't use git" or "looks like you inserted a secret/PHI/whatever into a file there, can't do that" type of hooks/callbacks. At least at the end of a message right?

It's the 17th! Today's the day! I've got my affairs in order. Ready to go!


# CODE IMPROVEMENTS
- unit testing <- IN PROGRESS
- integration testing <- TODO
- end to end testing <- DONE
- remove dead code
- replace sqlite with LanceDB for optimal multimodal persistence and vector similarity built in
- put a conversation history tool in the crow-mcp toolkit
- work on playwright integration <- this is an extremely high priority


# MCP TOOL NAME RESOLUTION
Updating the config.yaml in ~/.crow is not having the intended effect for the crow-cli-dist that we built with pyinstaller. Need to get to the bottom of why that is and work on playwright integration. Make the client side tools more robut so we can change names of tools needed for client-side execution easily without having to change ~/.crow/config.yaml, which isn't working right now. 

So we want to switch over officially to using the built distributable and fix the error which was keeping the windows version from being built in the github workflow. Right now this stuff is all over the place. Moving the the agent-client is going to require robust mapping of crow-mcp tools to the builtin, which isn't working right now. I don't think the pyinstalled package is even looking in ~/.crow/config.yaml? It doesn't appear to be anyway


yeah I can change the names in ~/.crow/config.yaml and it still isn't showing up as a client-side tool for crow-debug, which is bad. Going to have to do some serious reworking of that and if we are we might as well do for client-agent or agent-client

Mostly I think we need to do this without relying on hand modifying configs in ~/.crow. 

1. Check if there are other MCP servers loaded
2. If there are use the crow-mcp_* tool names
3. If there are not use terminal, edit, write, etc as tool names
4. Either way this is very very deterministic. When other MCP servers are added we load crow-mcp in a way that still maps to client capabilities and what we know are the names of crow-mcp

So yeah when we load crow-mcp inside the agent nothing has the crow-mcp_{tool_name} prefix, but whenever the client is exposing mcp tools we know it does

YEAH THE DIST VERSION BUILD WITH PYINSTALLER IS NOT LOADING IN CONFIG.YAML OVERRIDES!!! THIS IS NOW THE CENTRAL BUG.

# TOKEN STREAMING BUG
- First token not being received correctly - hiccup between thinking/reasoning content and normal content



# BUG FIXES
- **CRITICAL: KV cache corruption with images - Qwen3.5 hybrid model incompatibility**
  - **SYMPTOM**: llama.cpp logs `find_slot: non-consecutive token position X after X for sequence 3`
  - **EVIDENCE**: Reproducible bug where image token positions are off by 1 token
    - Text ends at position 44684, image should start at 44685
    - llama.cpp sees gaps: `find_slot: non-consecutive token position 44685 after 44684`
    - Checkpoint validation fails when restoring checkpoints near image position
    - Bug only triggers when checkpoint restoration position ≈ image position
  
  - **ROOT CAUSE**: SQLite persistence + images = fundamental mismatch
    - Images serialized to SQLite as base64 in JSON blobs
    - When reconstructing prompts from persisted data, token counting is off by 1
    - Qwen3.5's hybrid architecture (SWA + SSM) requires continuous token sequences for KV cache checkpoints
    - One-token gap breaks the checkpoint system, causing full prompt re-processing
  
  - **WHY IT MATTERS**: 
    - Hybrid models (Qwen3.5, etc.) use sliding window attention + recurrent memory
    - llama.cpp's checkpoint system expects exact token position tracking
    - SQLite base64 encoding/decoding introduces subtle token count discrepancies
    - Every multimodal conversation will eventually hit this bug
  
  - **REPRODUCIBILITY**: 100% - happens every time image is in conversation history
    - Bug triggers when: prompt with image + subsequent turn tries to restore checkpoint near image
    - Bug doesn't trigger with: text-only conversations, or when checkpoint is far from image
  
  - **FIX PLAN**: Refactor from SQLite to LanceDB for session persistence
    - **CURRENT ARCHITECTURE**:
      ```
      Session messages → SQLite (JSON blobs with base64 images)
      Load session → deserialize JSON → build prompt → llama.cpp → token offset → KV cache break
      ```
    
    - **NEW ARCHITECTURE**:
      ```
      Session messages → LanceDB (JSON blobs WITHOUT images)
      Images → ~/.crow/sessions/{session_id}/images/{image_id}.{jpg|png}
      Load session → fetch image from filesystem → build prompt with correct token positions → llama.cpp
      ```
    
    - **IMPLEMENTATION STEPS**:
      1. Create `~/.crow/sessions/{session_id}/images/` directory structure
      2. Store images as files, not in SQLite/LanceDB JSON blobs
      3. Update `Session.add_message()` to save image files separately
      4. Update `Session.load()` to reconstruct image references from filesystem
      5. Ensure token counting uses actual file-based images, not serialized base64
      6. Update `prompt.py` to load images from filesystem instead of deserializing base64
    
    - **WHY LANCEDB**:
      - Better JSON blob handling than SQLite (native JSON support)
      - Vector search for future context retrieval
      - More efficient for large JSON blobs
      - Better than SQLite for "conversation as JSON" pattern
    
    - **MIGRATION STRATEGY**:
      - Keep SQLite for backward compatibility during transition
      - New sessions use LanceDB
      - Gradual migration of existing sessions
    
  - **SHORT-TERM WORKAROUND** (until LanceDB refactor):
    - Clear KV cache before sending prompts with images
    - Don't persist image data through SQLite (store separately)
    - Force fresh prompt construction for multimodal turns
    
- adding a folder causes ACP to crash
- ~~when we cancel a session we do NOT want to include any crap in the messages might yield things like this so we need to revisit cancellation handling and think about letting that last token trickle in after all~~

- ~~apparently zed uses resource instead of resource_link now, which is fine by me lol. implemented. still having trouble doing for when there are multiple types of resource in the message~~

# BACKLOG
- doom loop detection
- Fix intermittent error in terminal tool since upgrade The key insight is that synchronous blocking code (like `time.sleep()` in the terminal polling loop) inside an `async def` function will block the entire event loop - which could cause hangs if the MCP transport needs to do I/O simultaneously. The fix would be `asyncio.to_thread()` or making the polling truly async. 





# DONE
- ~~refactor react~~ <- DONE
- ~~Fix system prompt to actually include AGENTS.md, render workspace info, add datetime~~
- ~~refactor configuration copy over at startup to use crow-cli/src/crow_cli/agent/default~~
- ~~Fix prompt_id being hard coded, actually use hash of unrendered~~
- ~~Include @-ed files in the context through /files or whatever~~
- ~~Add tool calls and executions token emission~~
- ~~Use AsyncOpenAI client to enable better `session/cancel` behavior~~
- ~~test `load_session` using local model~~
- ~~Make different providers part of the actual configuration <- use a toml file or something in ~/.crow~~
- ~~Add different models to NewSessionResponse(config_options<- put model choices here)~~
- ~~Revisit config option setting and build without using session.model_identifier~~
