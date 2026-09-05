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
- **LLM** — what the model sees: execute text (stdout + Out[n], cap ~5k
  tokens) with hydrated image_url blocks PREPENDED when vision tools ran.
  Images are first-class: tools DECLARE them via `llm_images()` returning
  ImageStore refs (content-addressed sha256 keys, same scheme as
  messages.extract_images — dupes dedupe free). No blob autodetection.

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
- [ ] 3. `subtool_calls` table (memory/models.py + migration, migrate_v6
       pattern): session_id, agent_id, parent_tool_call_id, cell_seq, tool,
       mode, args JSON (FULL fidelity — heavy bytes go to ImageStore by ref,
       never truncate/hash), acp_payload JSON, result_kind, result_ref,
       status, error, emitted, created_at. Register sink writes through at
       call time — the table is the queue, records survive a wedged kernel.
- [ ] 4. Drain + emission: execute/main.py reads parent tcid from _meta
       (agent/tools.py adds it), injects the begin_cell prologue, drains in
       a finally (partial cells still made real edits), emits ACP updates,
       marks emitted. react.py: prepend image_urls from drained vision refs
       (hydrate via crow_cli.memory like session messages). Cap execute
       output ~5k tokens.
- [ ] 5. write — diff payload, same pattern.
- [ ] 6. fs — modes: read (FileResult; polite "use vision.file" on images),
       glob (gitignore/.venv/.node_modules-aware — pathspec), search (rg),
       ast (ast_grep_py bindings — search AND replace; shadow-git when no
       git detected).
- [ ] 7. vision — modes: file, webcam (the robotics door — first class,
       never dropped), video later (video-frames skill as a mode: frame
       extraction -> N file results). Bytes -> ImageStore at call time;
       entries hold refs; llm_images() declares hydration.
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
- [ ] 13. Pare crow_cli.mcp to the single execute tool; system prompt
       rewrite around the omni tool.

## Hard-won caveats (from the session that started this)

- Kernel wedged twice + killed once by a stray-hunter: hard-stop reset is
  FOUNDATION, not a feature. Break-glass raw edit/terminal after N
  consecutive execute failures — single tool = single point of failure.
- Background-task output bleeds across cells -> identity at CALL time via
  contextvar, never at drain time.
- Kernel has a running loop: top-level await, never asyncio.run.
- Drain in finally: a cell that raised halfway still made real edits.
