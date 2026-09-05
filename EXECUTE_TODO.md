# EXECUTE_TODO — the omni-tool plan

Thesis: ONE MCP tool (`execute`). Everything else is Python — ambient in the
kernel via zero-day imports — observed through the subtool register and
re-emitted, so nothing is lost. `crow_cli.mcp` stays untouched until
`crow_cli.tools` is proven; then pare to the single tool and rewrite the
system prompt around it (help() is the just-in-time schema — proven
non-paging: ipykernel pydoc falls to plain stdout).

## The three-fold split (every tool call inside a cell)

- **Python** — what the code gets: result objects (truthy, compact repr for
  Out[n], real fields for reuse). Failures RAISE ToolError subclasses; no
  "Error: ..." strings — that's an MCP wire convention, not a Python one.
- **ACP** — what the client sees: `acp_payload()` JSON-native semantic dicts
  recorded by `@subtool`, rendered server-side by the drain into
  ToolCallStart/Progress (diffs via tool_diff_content, image blocks for
  vision). `crow_cli.tools` never imports acp. ACP v1 has no parent field on
  the wire: subcalls emit as siblings inside execute's window; lineage lives
  in the table (+ field_meta later).
- **LLM** — what the model sees: THE OUTPUT OF EXECUTE. Unmodified. Code
  output on success; traceback on failure (tools RAISE — they don't need
  their own guards because they run inside a properly guarded,
  defensively-coded MCP tool that catches and shows the error to the LLM).
  No tool injects anything into the text — an edit inside a cell costs
  zero extra LLM-side rendering; diffs are ACP-only. The ONE modification,
  the only reason the LLM side exists: when vision tools ran, hydrated
  image_url blocks are PREPENDED — without them vision models have no way
  to actually see images. The signal is a has_vision bool in effect: the
  drained llm_images refs (ImageStore keys, same content-addressed scheme
  as messages.extract_images — dupes dedupe free) non-empty. Tools DECLARE
  images via llm_images(); no blob autodetection, no repr markers. Memory
  returns polars DataFrames — execute's output renders them, done. ACP
  emission is a different story entirely: every subtool gets its proper
  semantic rendering (diffs, images, terminal stream).

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
       at ~5k tokens head+tail. execute_acp_execute drains via
       _emit_subtool_calls BEFORE its own completion update AND in the
       except branch (partial cells still made real edits). Emission:
       sibling ToolCallStart (id `<parent>/sub:<row id>`, kind from
       _SUBTOOL_KINDS, title `tool: path` for diffs else `tool/mode`) +
       update_tool_call with tool_diff_content for diff payloads; flips
       emitted in the same transaction as the SELECT. react.py image_url
       prepend DEFERRED to step 7 (vision) — nothing emits images yet.
       (Landed with step 7 — in execute_acp_execute itself, not react.py:
       the drain returns hydrated image_url blocks, the executor prepends
       them to the text result. react.py never needed to know.)
       Tests: 6 register-db unit, 2 new real-kernel (cross-process
       write-through, cap), 4 emission integration (focused drain x3 +
       full e2e: scripted LLM -> react loop -> real kernel -> `await
       edit(...)` -> row written by kernel process -> drained -> FakeConn
       saw sibling edit call with diff -> EditResult in the tool message).
- [ ] 5. write — diff payload, same pattern.
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
       VisionResult(key, mime, width, height, source) with a plain compact
       repr — an earlier draft put a `![image](crow-image://<key>)` blob
       in the repr as an "LLM marker"; RETRACTED — the llm_images refs on
       the row are the only signal the drain needs (has_vision in effect),
       repr markers are redundant noise. ACP channel: acp_payload
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
  binds the function. Use `sys.modules["crow_cli.tools.vision"]` in tests.
