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
- [x] 6a. fs — modes read/glob/search. LANDED: `fs(mode, path, pattern,
       offset, limit, file_pattern)` in tools/fs.py; FileResult (.content
       raw / .text numbered / .lines / .offset / .shown / .truncated),
       GlobResult (.paths), SearchResult (.matches of SearchMatch(path,
       line, text), .paths deduped, .text rendered). result_kind gained
       "read" and "search"; the drain maps ARTIFACT -> kind
       (`_KIND_BY_RESULT = {"diff": "edit", "read": "read", "search":
       "search"}`) and falls back to `get_tool_kind(row.mode or row.tool)`
       — kind must follow the mode for a multi-mode tool, since
       get_tool_kind("fs") is "other" and a FAILED row's result_kind is
       "error" (so a read that raised still arrives as a read call). Read
       emission mirrors execute_acp_read: located at the file, numbered text
       in a text block. glob/search emit text with no location.
       DEVIATION from the plan: glob is ripgrep (`rg --files -g`), NOT
       pathspec. pathspec is already a dependency but ships no gitignore
       walker (no nested .gitignore, no .git/info/exclude), so it meant
       reimplementing git semantics; rg gives them for free and is already
       the search engine — one external binary, two modes, and it is
       fail-fast (FsError) when absent rather than degraded.
       read ports `_is_binary_file`/`_format_with_line_numbers` from
       mcp/read (copied, not imported: mcp/read is endgame-deleted) and
       `_resolve_path` from mcp/editor (imported, like edit/write — the
       engine survives). Images refuse politely and point at
       vision(mode='file'); directories point at fs(mode='glob'); .svg is
       TEXT (readable — vision rejects it, fs does not).
       Tests: 22 unit (real files + real rg, no mocks), 4 drain (read
       located, search/glob text, failed-row kind), 1 kernel e2e (all three
       modes in a real subprocess), 2 prelude (ambient + runs), and the
       live-client e2e now asserts a read arrives at the client as
       kind="read" with the numbered text while the model sees it only
       because the cell printed it.
- [x] 6b. fs ast — `fs(mode="ast")` structural search and
       `fs(mode="rewrite")` structural transform, on the ast-grep-py
       binding. ast returns the SAME SearchResult shape as regex search
       (SearchMatch(path, line, text), match text whitespace-collapsed and
       capped at 160 chars because a structural match can span lines);
       rewrite returns RewriteResult (.files of EditResult, .paths,
       .changed, .scanned, .matches, .summary). The walk is rg --files
       (gitignore-aware, same excludes), narrowed by `lang=` or by every
       mapped extension; parsing + planning run in asyncio.to_thread.
       THREE DEVIATIONS from the plan, all deliberate:
       * NO multi-diff payload. A rewrite calls `write()` per changed file,
         so each file is its OWN row and its own edit-kind diff call on the
         client, and the rewrite's own row is the operation (pattern,
         rewrite string, summary text). One row carrying N whole files would
         have put megabytes of JSON in a single subtool_calls row for a
         300-file rewrite; N rows put the same bytes where the diffs already
         live. CONSEQUENCE: the drain's `content == "multi-diff"` branch now
         has no producer — candidate for deletion (see the simplification
         list at the bottom).
       * NO ImageStore preimage shadow. Each per-file EditResult carries
         whole old_text/new_text into its row's acp_payload, so crow.db IS
         the undo log for a rewritten tree, whether or not it is a git
         checkout. Storing the preimage a second time would duplicate it.
       * `lang` is VALIDATED against the extension map before anything
         reaches SgRoot: an unsupported language makes the native binding
         PANIC — pyo3_runtime.PanicException, a BaseException that sails
         through `except Exception` (and would swallow asyncio cancellation
         if caught broadly). Bundled grammars: python, javascript,
         typescript, tsx, jsx, rust, go, c, cpp, csharp, java, ruby, html,
         css, json, yaml, markdown, bash, kotlin, swift, php, lua, scala,
         elixir, haskell, dart, nix, solidity. NOT bundled (raise): sql,
         toml, zig, r, vue, svelte, erlang, qml, shell (it's "bash").
       Binding facts, verified: `SgRoot(src, lang).root()`;
       `root.find_all(pattern=...)`; `node.replace(text)` returns an Edit
       (start_pos/end_pos/inserted_text) and inserts LITERALLY — there is no
       fix engine, so metavar expansion is ours; `root.commit_edits(edits)`
       -> new source; `node.range().start.line` is 0-INDEXED; a bad pattern
       raises RuntimeError("cannot get matcher") -> FsError;
       `node.get_root()` returns an SgRoot (needs `.root()` again).
       THE METAVAR TRAP: `$$$REST` captures the punctuation nodes too
       ([b, ",", c] for `join(a, b, c)`), so joining capture texts gives
       `b, ,, c`. Expansion is the SOURCE SPAN — first capture's start index
       to last capture's end index, sliced out of the root text. And only
       metavars the pattern CAPTURED expand (`get_match(name) is None` ->
       left literal), which is ast-grep's own rule and why a JS template
       literal `${name}` survives in both source and rewrite string.
       Planning happens for every file BEFORE any write, so a bad pattern
       leaves the tree untouched.
       Tests: 14 more unit (36 total in test_tools_fs.py), 1 drain (the
       rewrite summary row is kind="edit" — get_tool_kind("rewrite") hits
       the "write" substring rule; pinned so a change there is a decision),
       1 kernel-level (the native extension loads in the kernel SUBPROCESS —
       the packaging-shaped failure in-process tests cannot see).
       pyproject.toml + uv.lock (ast-grep-py>=0.45.3) commit with this step.
- [x] 6c. BUG HUNT on 6a+6b — "step is not done until it is bugless".
       Probed every edge in a live kernel against scratch trees (newline-only
       file, limit=0, empty file, CRLF, 5000-char line, latin-1 content,
       non-UTF8 FILENAME, read-only file mid-rewrite, greedy nested pattern,
       endless producer, 120KB of stderr, /usr/share and the worktree at
       cap and uncapped). FIRST RING — nine bugs found and fixed, each with
       a regression test in test_tools_fs.py:
       (A) FileResult.shown derived from content.splitlines() -> stored field;
       (B) limit=0 rendered "showing lines 1-0" -> empty window, no notice;
       (C) overlapping ast matches spliced garbage -> _non_overlapping,
           outermost wins, .skipped counts the drops;
       (E) rg --json base64 `lines` -> _json_line;
       (F) rg --json base64 `path` blamed the root, and replace-decoded
           `rg --files` output returned paths that don't exist -> _json_path
           + _file_items, both os.fsdecode; plus _wire_safe in register so a
           lone surrogate cannot silently drop the row;
       (G) proc.communicate() buffered all of rg -> _rg_stream (streamed,
           capped, kills rg mid-flight);
       (G') THE BIG ONE, found by the regression test itself: after an early
           break the paused pipe transport means `await proc.wait()` in the
           finally NEVER RETURNS — a permanently wedged kernel, timing-
           dependent with rg and deterministic with `yes`. communicate().
       (H) read-only file mid-rewrite -> partial rewrite; writability is now
           pre-flighted in the plan.
       Then a SECOND ring, probed after the first was committed — four more,
       each with its own regression test (54 tests, +18 total):
       (I) limit flowed straight into `[:limit]`, so limit=-1 silently
           dropped the last line (read) or emptied the result while still
           claiming truncated (glob/search: cap=-1 trips `len(items) > cap`
           on the first match). A limit is a COUNT -> FsError if negative.
       (J) `fs("read", fifo)` HUNG: open() on a FIFO with no writer blocks,
           in a worker thread that cannot be cancelled. `not path.is_file()`
           -> FsError (also covers sockets and devices; a symlink to a
           regular file still reads).
       (K) THE KILL DID NOT REACH GRANDCHILDREN. `sh -c 'echo hit; sleep 30'`
           timed out, sh was SIGKILLed, and `sleep` kept stdout open — so the
           drain waited ~30s for an EOF that was not coming. Found by probing
           the timeout path, which wedged the kernel a second time.
           start_new_session=True + os.killpg(pid, SIGKILL): 1.00s, no orphan.
       (L) cancellation of a streaming search left the producer running and
           had to keep propagating CancelledError (the react loop depends on
           it) — pinned by a test that checks pgrep before and after.
       Non-bugs pinned by probing: empty file, binary in a walk (rg skips),
       dangling symlink (rg skips), long line (capped in .text, raw in
       .content), latin-1 on mode="read" (FsError, by design — code can
       read_bytes().decode()), .svg is text (vision refuses it, fs does not),
       no-op rewrite (changed=0 with matches>0 reads as "pattern hit,
       rewrite changed nothing" — documented on RewriteResult), negative
       offset (clamped to 1, unlike a negative limit).
       Sweep: 663 passed.
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
  `sys.modules["crow_cli.tools.vision"]` in tests and cells — or
  `from crow_cli.tools.vision import _helper`, which is SAFE (verified: the
  from-form resolves through sys.modules, only the `as` form goes through
  getattr on the poisoned package dict). Same trap in
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
- ripgrep's `-g` glob is matched against the path RELATIVE TO THE PROCESS
  CWD, not relative to the search path you pass. `rg --files -g
  'src/tools/*.py' /abs/root` returns NOTHING when the cwd is anywhere else,
  while `-g '*.py'` (slashless — matches at any level) works and hides the
  bug. fs therefore runs rg with `cwd=root` and `.` as the path, then
  absolutizes the output (`str(root / rel)`; pathlib collapses the leading
  `./`, and `--json` paths come back as `./src/...`). Also `--sort path` on
  both modes: rg searches in parallel, so unsorted output order is
  nondeterministic and any test asserting hit order flakes. And
  `--no-config`, or the user's ~/.ripgreprc changes the tool's behaviour.
  Exit 1 is "no matches", not failure — only >=2 is an error.
- KILLING AN ASYNC SUBPROCESS IS NOT ENOUGH — DRAIN IT. Breaking out of
  `async for line in proc.stdout` early leaves the StreamReader over its
  high-water mark (64KB), which PAUSES the pipe transport: it comes off the
  selector, so EOF is never observed and `await proc.wait()` blocks FOREVER.
  Not a slow tool call — a wedged kernel, recoverable only by reset.
  `yes hit` reproduces it in one line (measured: `wait()` HUNG >5s,
  `communicate()` returned in 0.000s with rc=-9); rg reproduces it whenever
  the reader happens to be paused at the break, which is timing, so it flares
  in production and not in tests. After `proc.kill()`, `await
  proc.communicate()`: draining resumes the transport and reaps the child.
  Same deadlock from the other side: stderr must NOT be a pipe nobody drains
  (a child writing more than the pipe buffer blocks and takes the loop with
  it) — fs sends stderr to a `tempfile.TemporaryFile()`.
  AND THE KILL MUST REACH THE PROCESS GROUP: `proc.kill()` hits the direct
  child only, so a grandchild that inherited stdout (`sh -c 'echo hit; sleep
  30'`, or rg with a `--pre` preprocessor) keeps the pipe open and the drain
  waits ~30s for an EOF that is not coming. Start the child with
  `start_new_session=True` and kill with `os.killpg(proc.pid, SIGKILL)`
  (fall back to `proc.kill()` on ProcessLookupError/PermissionError). Measured:
  30s hang -> 1.00s, and `pgrep -f` shows no orphan. Cancellation goes through
  the same finally, so a cancelled cell leaves nothing running either.
- open() ON A NON-REGULAR FILE BLOCKS FOREVER. A FIFO with no writer, a
  socket, a device: `open()` waits, and in `asyncio.to_thread` that is a
  worker thread which CANNOT be cancelled — the cell hangs, the loop is fine,
  and reset is the only way out. `path.is_file()` is the guard (False for
  pipes/sockets/devices and for a dangling symlink, True for a symlink to a
  regular file). Same class of bug as the subprocess drain: not a wrong
  answer, a wedged kernel.
- A LIMIT IS A COUNT, NOT A SLICE END. Passing the caller's `limit` straight
  into `window[:limit]` means -1 silently drops the LAST line and a search
  comes back empty while still claiming truncated (cap=-1 satisfies
  `len(items) > cap` on the very first match). Validate at the cap helper,
  once, for every mode. Offsetting is different: a negative or past-EOF
  offset is clamped, because "start at the beginning" is a sane reading of it.
- rg --json BASE64s what it cannot emit as UTF-8, and it does so for `path`
  AND for `lines` (`{"bytes": "<b64>"}` instead of `{"text": ...}`). Taking
  only `.text` yields `""`: a latin-1 match renders as an empty line, and an
  empty path joined onto the root BLAMES THE ROOT DIRECTORY for a hit inside
  it. Decode both.
- For PATHS the decode is `os.fsdecode` (surrogateescape), never
  `decode(errors="replace")`: a replacement character makes a path that looks
  fine and does not exist, so glob hands back unopenable paths and an ast
  walk skips the file without a word. fsdecode keeps it real and openable —
  and then a lone surrogate CANNOT CROSS THE WIRE: json.dumps escapes it to
  `\udcff`, which is invalid JSON to a Rust/serde client, and register's
  write-through (catch + log) would drop the row SILENTLY. Hence
  `_wire_safe` at the row choke point: the DB row gets `?`, the kernel-side
  result object keeps the truth.
- ast-grep matches the `module` node. A bare-metavar pattern (`$CALL`)
  matches every node that fits, nested ones included — 9 matches for
  `f(g(x))`, outermost being `module [0:8]` whose text is the whole file
  INCLUDING the trailing newline. `commit_edits` on overlapping ranges does
  not complain, it splices garbage, so fs de-overlaps (outermost wins, left
  to right, like re.sub) and counts the drops in `.skipped`. The output
  `wrapped(f(g(x))\n)` is the FAITHFUL expansion of that one applied match,
  not corruption — which is exactly what made the bug hard to see.
- A REWRITE MUST BE ALL-OR-NOTHING: `os.access(path, os.W_OK)` is checked
  inside the PLAN, so one read-only file fails the whole rewrite before any
  write. Without the pre-flight, a.py came back transformed and b.py raised
  WriteError — a half-rewritten tree, the worst of both outcomes.
- A COUNT DERIVED FROM A RENDERED STRING LIES. `shown=len(content.
  splitlines())` reported 0 for a window holding one empty line, because
  `"\n".join([""])` is `""` — so a newline-only file claimed
  lines=1/shown=0/truncated=True while .text still rendered `1→`. Anything
  the caller reasons about (.shown, .truncated) is a stored field.

## Pending decisions — these DELETE landed code, so they wait for a yes

1. `register._entries` / `pending()` / `drain()` are dead in production: the
   DB table is the queue (write-through at call time, the server drains by
   parent tcid). The in-kernel list is a second source of truth that only
   kernel-local tests read (tests/mcp/test_execute_prelude.py asserts on
   `drain()`, tests/unit/test_tools_*.py on `pending()`). Deleting it means
   rewriting those assertions against the table.
2. The drain's `content == "multi-diff"` branch has no producer since 6b
   chose per-file write rows over one N-file payload. Delete the branch (and
   `_subtool_id`'s `part` argument) or keep it as the documented way to emit
   one call per artifact from a single row.
3. `acp_payload()` is redundant for the diff tools — the drain needs exactly
   EditResult's fields. RECOMMEND KEEP: it is what keeps crow_cli.tools
   acp-free, and it is the seam a new artifact type plugs into.
4. `_emit_subtool_call` sends three beats (pending / in_progress /
   completed) where two would do. RECOMMEND KEEP at three: it is byte-for-byte
   the shape crow sends for a real edit call, and the client merges them.
