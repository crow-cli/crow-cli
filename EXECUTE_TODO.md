# EXECUTE_TODO — the omni-tool plan

Thesis: ONE MCP tool (`execute`). Everything else is Python — ambient in the
kernel via zero-day imports — observed through the subtool register and
re-emitted, so nothing is lost. `crow_cli.mcp` stays untouched until
`crow_cli.tools` is proven; then pare to the single tool and rewrite the
system prompt around it (help() is the just-in-time schema — proven
non-paging: ipykernel pydoc falls to plain stdout).

## The three-fold split (every tool call inside a cell)

- **Python** — what the calling code gets: result objects (truthy, real
  fields for reuse — EditResult.diff/.added, VisionResult.image as a PIL
  Image). Failures RAISE ToolError subclasses; no "Error: ..." strings —
  that's an MCP wire convention, not a Python one. NO designed reprs:
  display strings are not a channel.
- **ACP** — what the client sees: `acp_payload()` JSON-native semantic dicts
  recorded by `@subtool`, rendered server-side by the drain into ONE
  SYNTHETIC TOOL CALL PER ROW — the pretty face. Each goes out shaped like
  a call the LLM made: `start_tool_call(<turn>/call_sub<row>, title,
  kind=get_tool_kind(tool), status="pending", locations=[path],
  raw_input=row.args)` -> in_progress carrying the artifact (diff via
  tool_diff_content, image via tool_content(image_block), failure text via
  tool_content(text_block)) -> completed/failed. A multi-diff payload earns
  one call per file (`call_sub<row>_<part>`).
  Why siblings, not a union list on execute's own call (that was built, then
  reversed): the client renders ONE ToolCall widget per toolCallId
  (tui/widgets/conversation.py on_acp_tool_call_update, keyed by
  encode_tool_call_id) and post_tool_call renders a DiffView per diff
  content — so a union list did render, but as "execute printed some
  diffs". A diff has to arrive as the output of AN edit/write call to look
  like what it is: attributed, titled, located, with the code's own args on
  rawInput. The 1-1 LLM<->ACP mapping is NOT broken by synthetic ids,
  because the LLM never sees the ACP stream — subtool calls are not
  recorded as conversation, they are code. Lineage lives in the table
  (parent_tool_call_id); ACP v1 has no parent field on the wire.
  `crow_cli.tools` never imports acp.
- **LLM** — what the model sees: WHAT THE CELL PRINTED. stdout + stderr,
  or the traceback on failure (tools raise; execute is the guard). The
  kernel drains execute_result (Out[n]) off iopub and DISCARDS it — the
  REPL's display of the last expression is a notebook affordance, not
  program output, and it fired only by the accident of expression
  position. The ONE modification, the only reason the LLM side exists:
  vision ran (drained llm_images refs non-empty — has_vision in effect)
  -> hydrated image_url blocks PREPENDED, or vision models are blind.
  1-1 with ACP: same refs render as image_url (LLM) and image content
  blocks (client). Memory returns polars DataFrames; code prints what it
  wants the model to see. Parallel tool calls (asyncio.gather) hold up:
  contextvar identity is inherited by tasks, every call writes its row,
  the drain emits siblings in row order.


Identity: per-cell prologue `begin_cell(session_id, parent_tool_call_id,
cell_seq)` injected by execute before the model's code — model never sees,
cannot forge (same rail as `_meta` in agent/tools.py execute_acp_execute,
which already passes cwd + session_id; parent tcid = ctx.tcid(...) joins
that dict). Drain key = parent_tool_call_id; session_id indexes the table.
Stamped at CALL time via contextvar so async tasks spawned in-cell inherit
it and background work never bleeds into the next cell's drain.

## Steps

- [x] 1. `crow_cli/tools/` skeleton — register.py (@subtool, begin_cell,
       drain/pending/clear, SubtoolEntry), results.py (ToolResult protocol,
       ToolError, EditResult), lazy facade __init__.py + PRELUDE.
- [x] 2. tools/edit.py — imports the mcp editor engine (replace/_resolve_path,
       already pure + raising), returns EditResult, raises EditError. Prelude
       wired into execute get_kernel (start AND reset). Tests: 9 unit +
       4 real-kernel, all green; existing test_execute.py unaffected.
- [x] 3. `subtool_calls` table (memory/models.py — no migration script:
       create_database is create_all, additive, and runs on production
       startup at agent/memory.py + tui/db.py): session_id, agent_id,
       parent_tool_call_id, cell_seq, tool, mode, args JSON (FULL fidelity —
       heavy bytes go to ImageStore by ref, never truncate/hash),
       acp_payload JSON, result_kind, status, error, emitted, created_at.
       Register sink writes through at call time (begin_cell gained db_uri;
       cell_seq auto from IPython execution_count) — the table is the queue,
       records survive a wedged kernel. Sink is fail-open: unwritable DB
       logs a warning, the in-memory entry still stands, the tool works.
- [x] 4. Drain + emission: execute/main.py reads parent tcid + db_uri from
       _meta (agent/tools.py execute_acp_execute injects both), prepends the
       begin_cell prologue to every non-empty cell (fail-open), caps output
       at ~5k tokens head+tail.        execute_acp_execute drains via _emit_subtool_calls BEFORE its own
       completion update AND in the except branch (partial cells still
       made real edits). Emission (REVISED TWICE per the plan-person:
       siblings -> union list -> back to SIBLINGS after reading the
       client): the drain emits one synthetic tool call per row and
       RETURNS only llm_blocks, which prepend to the LLM view; execute's
       own completion carries nothing but its printed output. Flips
       emitted in the same transaction as the SELECT.
 react.py image_url
       prepend DEFERRED to step 7 (vision) — nothing emits images yet.
       (Landed with step 7 — in execute_acp_execute itself, not react.py:
       the drain returns hydrated image_url blocks, the executor prepends
       them to the text result. react.py never needed to know.)
       Tests: 6 register-db unit, 2 new real-kernel (cross-process
       write-through, cap), 8 emission integration (focused drain: diff,
       text+failed, parallel row order, image, dead ref, other parents;
       plus react-loop e2e with a real kernel: single edit, gather x3,
       vision), AND ONE REAL CLIENT — tests/e2e/test_execute_acp_client.py
       spawns a real agent subprocess (SubagentDriver: this interpreter, so
       agent + MCP server + kernel are all live code) and asserts on the
       session_update stream the client actually receives: a `call_sub<N>`
       tool call with kind="edit", title, locations, rawInput = the args
       the CODE passed, and a FileEditToolCallContent diff — while
       execute's own completion carries only the printed text. In-process
       tests cannot catch deployment-shaped failures (a stale MCP server
       with no prologue, a db missing subtool_calls): everything still
       passes while the client sees nothing. This tier can.
- [x] 5. write — diff payload, same pattern. LANDED: returns EditResult
       (a write IS a diff — old_text "" for new files, previous content
       for overwrites; parent dirs created; binary-ish files diff against
       empty), raises WriteError. Kind comes from get_tool_kind("write") =
       "edit", so emission needed zero changes. 7 unit tests + ambient
       prelude check. Docstring carries the print contract (the model sees
       only what the cell prints; the client gets the diff regardless).
       THE ORPHAN: tests/unit/test_tools_write.py was committed in
       4223945e but write.py and its facade/PRELUDE registration were not
       — `git commit -a` stages TRACKED files only, so a brand-new module
       silently stays out and HEAD shipped a test importing a module that
       did not exist. `git status` for untracked sources before committing.
- [x] 5b. `crow_cli.tools.reload()` — the self-reloading harness, wired into
       PRELUDE so it runs on every kernel start AND reset. An agent can now
       edit a subtool and use the new code on the next line of the same
       cell, no reset, no restart. Tested at kernel level (3 tests in
       tests/mcp/test_execute_prelude.py: ambient on start, facade-cache
       purge + re-execution, identity rail preserved through a mid-cell
       reload with a real edit writing its row afterwards). See the
       PICKING UP HARNESS CHANGES caveat for the three traps and the two
       test-author traps.
- [ ] 6. fs — modes: read (FileResult; polite "use vision.file" on images),
       glob (gitignore/.venv/.node_modules-aware — pathspec), search (rg),
       ast (ast_grep_py bindings — search AND replace; shadow-git when no
       git detected).
- [x] 7. vision — modes: file, webcam (the robotics door — first class,
       never dropped), video later (video-frames skill as a mode: frame
       extraction -> N file results). Bytes -> ImageStore at call time;
       entries hold refs; llm_images() declares hydration.
       LANDED (file+webcam; video still pending): signature is
       `await vision(mode="file", path=...)` / `vision(mode="webcam",
       device_index=6)` — explicit kwargs beat a union-args list
       (self-documenting, `help()` reads clean, _bind_args records
       faithfully, @subtool gained dynamic mode from the runtime arg).
       VisionResult(key, mime, width, height, source); code gets a real
       image via .image (PIL Image loaded from the store — pillow added
       as a dep). An earlier draft put a `![image](crow-image://<key>)`
       blob in a custom repr as an "LLM marker"; RETRACTED twice over —
       first the blob, then the whole designed-repr idea: the llm_images
       refs on the row are the only signal the drain needs (has_vision in
       effect), and execute's output is what the cell PRINTED, nothing
       else. ACP channel: acp_payload
       {"content":"image", key, mime} -> drain hydrates bytes from the
       ImageStore -> tool_content(image_block(...)) on the sibling call
       (ToolCallProgress.content takes ContentToolCallContent WRAPPERS,
       not bare blocks — pydantic silently drops them otherwise). LLM
       channel: drain RETURNS hydrated image_url blocks; execute_acp_
       execute PREPENDS them to the text result (step 4's deferred half —
       done). images_dir rides the meta rail (server derives it exactly
       like agent/memory.py: sqlite -> db parent / "images"); kernel side
       is FsImageStore by design — the server's HybridReadStore fs
       fallback means kernel-written blobs hydrate even with S3 primary.
       Key scheme shared: memory/messages.py image_key() now used by BOTH
       extract_images and vision — same bytes, same key, cross-process
       dedupe free. cv2 runs in asyncio.to_thread (blocking C off the
       kernel's loop). File mode keeps the old MCP tool's 1568px cap +
       re-encode normalization.
- [ ] 8. web — modes: search, fetch, run (playwright python bindings).
- [ ] 9. memory — modes: list, search, sql (read-only conn -> polars
       DataFrame). Python objects, not LLM-markdown strings.
- [ ] 10. rlm — delegate rebuilt on session/fork (+load): relative offset
       (fork N messages back so history doesn't end in the fork call — no
       infinity mirror), fork call redacted from forked history, depth
       budget in session meta, blocking (response = last content block after
       final tool call) + async (handle; memory(session_id=...) to collect).
       Code tool, not MCP.
- [ ] 11. `!`/shebang lines -> terminal backend directly (pty, caps,
       logging, register entry as tool="terminal") — extracted pre-kernel;
       IPython never sees them. NOT system_raw (no pty/caps/telemetry).
       Proof it already routes: bare `ls -l` in execute came back with ANSI
       colors — tty-only colorization means pty means terminal stack.
- [ ] 12. ACP v2: execute transitions to terminal-type — full stream to
       client, coalesced ANSI-stripped result for LLM. Register/drain
       unchanged; emission timing changes.
- [ ] 13. THE ENDGAME: everything but `execute` moves into crow_cli.tools
       with zero-day autoload (PRELUDE) — crow_cli.mcp gets pared to the
       single execute tool; the old MCP tool wrappers (edit/write/read/
       terminal/web_*/capture_webcam/read_image_file/memory tools) come
       off the server registration; system prompt rewritten around the
       omni tool (help() is the just-in-time schema). The LLM's tool list
       is ONE entry. Nothing is lost: ACP emission covers the client,
       execute output covers the model.

## Hard-won caveats (from the session that started this)

- Kernel wedged twice + killed once by a stray-hunter: hard-stop reset is
  FOUNDATION, not a feature. Break-glass raw edit/terminal after N
  consecutive execute failures — single tool = single point of failure.
- Background-task output bleeds across cells -> identity at CALL time via
  contextvar, never at drain time.
- Kernel has a running loop: top-level await, never asyncio.run.
- Drain in finally: a cell that raised halfway still made real edits.
- SQLAlchemy trap: `Connection.execute(select(ORMClass)).scalars()` yields
  first-column ints (Row tuples, no identity map) — drain iterates Rows
  directly; tests use `sessionmaker` + expunge for detached attribute access.
- fastmcp Client CallToolResult spells it `is_error`, not MCP's `isError`.
- ACP pydantic SILENTLY DROPS bare content blocks in ToolCallProgress
  .content — the union is Content|FileEdit|Terminal ToolCallContent;
  images must ride `tool_content(image_block(...))`. No validation error,
  just an empty list on the wire. Check the wire, not the constructor.
- The tools facade caches resolved FUNCTIONS into `crow_cli.tools.__dict__`,
  shadowing same-named submodules: `import crow_cli.tools.vision as vmod`
  binds the FUNCTION, not the module. Use
  `sys.modules["crow_cli.tools.vision"]` in tests and cells. Same trap in
  reverse under importlib.reload: reload re-executes a module in its
  EXISTING dict, so cached facade functions survive it — purge the `_LAZY`
  keys from `crow_cli.tools.__dict__` before resolving the names again.
- OUT[n] IS NOT A CHANNEL (the carve-out): CrowKernel drains
  execute_result off iopub and discards it; execute returns stdout +
  stderr or the traceback. print() is how code talks to the model. Custom
  __repr__s on result objects were MCP-brain leaking into execution-brain
  (a tool-result voice for something that is CODE, firing only by the
  accident of expression position) — deleted; default dataclass repr is
  display for a human at the REPL, nothing more. Tests that asserted
  repr-in-output were encoding the wrong contract and got rewritten to
  print. Parallel tool calls (asyncio.gather) are first-class: contextvar
  identity inherits into tasks, every call writes its row, drain emits
  siblings in row order, image refs hydrate once.
- PICKING UP HARNESS CHANGES MID-SESSION is now HARNESS, not a hand recipe:
  `crow_cli.tools.reload()` re-imports every tool module from source in the
  LIVE kernel and rebinds the names into the kernel namespace, and PRELUDE
  is `from crow_cli.tools import reload; reload()` — so it runs on every
  kernel start AND every reset ("clear cached nonsense"). Mid-cell, just
  call `reload()`: variables, imports, cwd and execution_count all survive
  (verified live: a docstring changed with the in-kernel edit tool showed up
  on the next line). Scope is crow_cli.tools.* — the subtools, which is
  exactly what the kernel can own. The MCP server (prologue, output cap) and
  the agent (drain, ACP emission) are separate long-lived processes and need
  a restart; changes to modules the tools IMPORT (crow_cli.mcp.editor's
  engine, crow_cli.memory) need a kernel reset. Three traps it handles:
  * the facade is LAZY, so a fresh kernel has imported nothing but the
    package — reload must IMPORT-if-absent, not skip (skipping then
    `getattr(sys.modules[m], a)` = KeyError in the prelude, and the prelude
    is best-effort so the kernel came up with NO tools and only a truncated
    `output[:200]` warning to show for it);
  * importlib.reload re-executes in the EXISTING dict, so the facade's
    cached functions survive it — purge `_LAZY` keys from the package dict;
  * reloading register re-creates its contextvar and drops
    _sink_uri/_images_dir, silently killing the rail for the rest of the
    cell — capture the identity first, RE-APPLY begin_cell after.
  And one for test authors: reload creates NEW class objects, so (a) never
  test it in-process (other modules' collection-time `from ... import
  WriteError` + `pytest.raises` stop matching, and pytest-randomly shuffles
  the order) — test it in the kernel subprocess; (b) don't assert
  `before == after` on a reloaded dataclass, dataclass eq requires class
  identity. Compare fields.
- DEPLOYMENT SHAPE — the rail needs THREE processes on this tree's code and
  only one of them is the kernel: the AGENT (meta injection + drain), the
  MCP SERVER (prologue + sink config) and the KERNEL (the tools). A live
  session diagnosed here had an agent from the main tree (no drain at all)
  and an MCP server started 06:01, before _prologue landed at 08:02 — so no
  begin_cell, `register.current_cell()` None, zero rows, zero diffs, and
  every in-process test still green. Detect from inside a cell:
  `"_crow_begin" in globals()` (the prologue's own import) and
  `sys.modules["crow_cli.tools.register"].current_cell()`. Fix: restart the
  agent from this tree's venv; server and kernel follow. A stale server also
  pins the PRELUDE string it read at import time, so `reload` won't be
  ambient in that kernel either — bootstrap it once with
  `importlib.reload(sys.modules["crow_cli.tools"]).reload()` (re-executes
  __init__ from current source WITHOUT purging sys.modules, so the identity
  capture inside reload() still sees register).
- A spawned child agent comes up with ZERO tools unless the client passes
  mcp_servers to session/new — cli/main.py does
  `fastmcp_config_to_acp_servers(config.mcp_servers)`, while
  SubagentDriver.new_session defaults to []. With no tools the model emits
  its tool call as TEXT and the turn ends at once: looks like a model
  failure, is a wiring failure. Read the child's "Created session ... with
  N tools" log line first.
