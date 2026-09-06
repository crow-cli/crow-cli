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
  kind=_KIND_BY_RESULT[result_kind] or get_tool_kind(mode or tool),
  status="pending", locations=[path],
  raw_input=row.args)` -> in_progress carrying the artifact (diff via
  tool_diff_content, image via tool_content(image_block), failure text via
  tool_content(text_block)) -> completed/failed. Kind follows the ARTIFACT
  (result_kind) first, because one name doing read/glob/search/rewrite/sub
  cannot be classified by name — see 6d. ONE ROW IS ONE CALL: a tool
  that touches N files records N rows (fs rewrite and sub do exactly that,
  via write()), so there is no "many artifacts in one row" payload shape — it
  was built as `multi-diff`, never gained a producer, and is now deleted.
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
         live. RATIFIED by the plan-personified, and the consequence is now
         acted on: the drain's `content == "multi-diff"` branch (and
         `_subtool_id`'s `part` argument) are DELETED — one row, one call.
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
       the "write" substring rule; pinned so a change there is a decision.
       SUPERSEDED BY 6d: kind now comes from _KIND_BY_RESULT["rewrite"], and
       the substring rule would file its sibling "sub" under "other"),
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
       THIRD RING — one more bug, plus two silent-corruption classes that
       probing found CORRECT and therefore pinned (57 tests, +21 total):
       (M) `~` was never expanded: `Path("~/x").is_absolute()` is False, so
           it became `<cwd>/~/x` and failed with a path that reads like a bug
           report. Fixed in `_resolve_path` — the choke point that edit,
           write and the old MCP read all share, so all of them get it (136
           tests across those tools still pass).
       PINNED, NOT FIXED: ast-grep's `range().start.index` is a CHARACTER
           offset, not a byte offset — `_expand` slices a Python str with it,
           so a byte offset would mangle every file with accents or CJK in
           it, silently, and only for those files (fixture: a 35-byte,
           27-character first line). And a tree containing a SYNTAX ERROR
           parses partially and rewrites fine — tree-sitter ERROR nodes are
           not fatal, which matters because a pyo3 panic is a BaseException
           and would take the kernel with it.
       Also observed live: reload() does NOT pick up a change to a module the
       tools import (see the mid-session caveat, corrected).
       Sweep: 666 passed.
- [x] 6d. fs sub + dry_run — "make it a whole lot better". The modes were a
       2x2 with a hole in it:
                            find        replace
           by regex         search      — nothing —
           by syntax        ast         rewrite
       No multi-file TEXT replace, so "rename this env var across every
       .toml" was impossible: edit is one file and needs an exact string,
       rewrite needs a grammar, and toml/sql/ini/vue/svelte/zig/r/erlang/qml
       have none. LANDED:
       (a) `fs(mode="sub", pattern=<python regex>, rewrite=<replacement
           template>)` — the missing quadrant. Deliberately NOT
           `_candidates()`: the point of sub is the files ast-grep cannot
           parse, so the walk is narrowed only by file_pattern. The
           replacement is re's own template (\1, \g<name>) — inventing a
           second metavar syntax next to ast-grep's $A would be one more
           thing to remember and one more way to be wrong.
       (b) `dry_run=` on BOTH replace modes — plan every file, report what
           would change, write nothing. `.files` holds real EditResults with
           real diffs (`_planned_edit` renders byte-identically to write(),
           pinned by a test that diffs a dry run against the real run), and
           NO diff reaches the client: nothing happened to the files, and a
           diff view over an untouched file is a lie.
       (c) `RewriteResult.diff` — every changed file's unified diff,
           concatenated. The LLM's half of a multi-file replace: the
           per-file diffs go to the CLIENT on their own calls and the model
           sees only what the cell printed, so `print(r.diff)` is how it sees
           what it did (or, with dry_run, what it is about to do).
       (d) `RewriteResult.result_kind = "rewrite"` (was "text") plus
           `_KIND_BY_RESULT["rewrite"] = "edit"`. Kind follows the ARTIFACT,
           not the name: get_tool_kind's substring rules file "rewrite"
           under edit only because it happens to contain "write", and "sub"
           under "other". Adding "sub" to that shared list is not an option —
           "subagent"/"task_submit" would become edits. Both replace modes
           also grew `.syntax` ("ast"|"regex"), and the summary says
           "parsed" vs "scanned" accordingly.
       BUGS FOUND BY PROBING THE NEW CODE (all fixed, all pinned):
       (N) `dry_run=True` on mode="read" was silently ignored — the guard
           lived inside the walk-mode branch, so read never saw it. The mode
           is now validated once up front (`_MODES`), the cross-cutting
           dry_run rule is checked before any mode runs, and the walk branch
           lost its wrapper (an unknown mode + dry_run reports the mode,
           which is the more useful complaint).
       (O) A bad replacement template escaped as a raw `re.PatternError`
           (\9) or a bare `IndexError` (\g<nope>) from inside a thread, deep
           in a loop over the caller's tree. re parses the template even
           when nothing matches, so one probe on "" validates it before a
           single file is read -> FsError("cannot apply replacement ...").
       (P) `rewrite=""` — sed's s/x//g, a legitimate deletion — was refused
           as a missing argument, because the guard tested falsiness. Now
           `rewrite is None`, the only check that can tell them apart.
       (Q) THE SILENT ONE, and it was not new: `_read_text` used the default
           newline= translation, so a CRLF file came back with EVERY line
           ending flipped to LF — and the diff HID it, because unified_diff
           is fed splitlines(), which strips \r from both sides. One word
           replaced, whole file reformatted, nothing to show it. Affects sub
           AND rewrite (shared reader). Fixed with newline=""; a
           multi-line-spanning ast match ($$$BODY across CRLF) is pinned too.
       (R) The same class one level up, in tools earlier steps shipped:
           write() read its preimage with the default translation, so
           crow.db's undo log held an LF copy of a CRLF file (restoring it
           would reformat the very file it claims to undo), and it wrote
           with the default translation, which on Windows turns \r\n into
           \r\r\n. Both now newline="". edit() was worse — ONE edit to a
           CRLF file reformatted all of it (verified live: b'x = "NEW"\ny =
           2\n' out of a b'...\r\n' file). It now reads faithfully and
           translates the CALLER's strings into the file's dominant ending
           (`_in_file_endings`), which is what has to happen because the
           model saw the file through read, which normalizes for display.
           The legacy mcp/editor/main.py has the same bug and is deleted in
           step 13 — left alone on purpose.
       REJECTED, with reasons (do not re-litigate):
       - Sequence protocol / "chainable" results (__len__/__getitem__/
         __iter__): vetoed — "it's python! it's like a million times more
         chainable than grep".
       - `fs(mode="tree")`: ASCII art is aesthetics. A flat gitignore-aware
         glob list is what a model actually wants, and
         directory_tree.DisplayTree in agent/prompt.py already feeds the
         system prompt at depth 3.
       - `context=` on search (grep -C): real, but cost > value right now —
         rg --json interleaves `context` records BEFORE their match, which
         fights the streaming parser. Future candidate.
       Scale, live: 585 files / 923 matches planned in 0.14s on a dry run
       over this repo.
       Tests: fs 57 -> 74, plus 3 in test_tools_edit, 1 in test_tools_write
       and a drain test proving a sub row emits kind="edit" while
       get_tool_kind("sub") says "other". Sweep: 688 passed.
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
- [x] 8a. web search + fetch — `crow_cli.tools.web`, modes "search" and
       "fetch". Ports mcp/web_search and mcp/web_fetch; NO new dependency
       (httpx, readabilipy and markdownify are already deps). Decisions:
       * ONE query per call, not `queries: list[str]`. The MCP tool looped
         over queries SEQUENTIALLY; in the kernel the model writes
         `await asyncio.gather(*[web("search", q) for q in qs])` and gets
         real parallelism plus one result object per query. Same reasoning
         that killed pagination.
       * PAGINATION DIES. `start_index`/`max_length` existed only because an
         MCP tool must return one string; here `.markdown` is the whole page
         and the model slices it in Python. `.text` is a WINDOWED rendering
         (first N chars + how many are left) so `print(r.text)` cannot flood
         the context, while `r.markdown` stays the truth — the same
         content/text split FileResult already draws.
       * `raw=True` is deleted, not fixed: the MCP flag never worked (the
         content variable was already overwritten with the extraction) and
         `.html` is simply always there.
       * A page is not a file, so `result_kind = "web"` and NOT "read": the
         read branch stamps `locations=[path]`, and a URL in a path field is
         a lie. kind still comes out "fetch" for free —
         get_tool_kind("fetch") hits the fetch/download rule, so no
         _KIND_BY_RESULT entry is needed (unlike "sub", the mode name here
         is exactly what the substring rules were built for).
       * The drain's generic else branch grows one honest line: a payload
         may carry `"subject"` (a URL, a query) and the title becomes
         "web/fetch: https://…". Not `path` — a subject is displayed, never
         claimed as a location.
       BUGS IN THE CODE BEING PORTED (all six fixed here, all pinned):
       (a) web_search leaks an AsyncClient per call (no `async with`).
       (b) `if i == limit - 1: break` returns EVERYTHING when limit=0.
       (c) the docstring says `limit: int = 5`, the signature says 10.
       (d) `is_html` treats a MISSING content-type as HTML, so a JSON API
           that omits the header gets fed to readability and comes back
           mangled. Fixed: a declared type is believed; only an undeclared
           body is sniffed for "<html".
       (e) `except Exception: return f"Error fetching {url}: {e}"` — the MCP
           wire convention. Here it raises WebError.
       (f) `response.raise_for_status()` inside the try becomes a bare
           "Error fetching" string, so a 404 and a DNS failure are
           indistinguishable; WebError carries the status.
       SearXNG at $SEARXNG_URL (default http://localhost:2946, verified UP).
       Down is an error that names the URL, not an empty result — web search
       is not optional equipment (see the searxng skill).
       LANDED, and the probe found five more (letters continue the run):
       (S) THE FACADE, not web.py: `pkg.web` handed back the MODULE.
           reload()'s import-if-absent loop reads the RUNNING module's _LAZY,
           while the binding loop at the bottom reads the freshly reloaded
           one — so a tool just added to _LAZY is first imported down there,
           and a first import makes importlib setattr(parent, child, module)
           AFTER the purge had already run. The bare name worked (it is bound
           from getattr on the submodule), only attribute access broke, which
           is why it survived until the first live probe of a new tool. Fix:
           purge LAST. Pinned by test_reload_purges_a_tool_that_is_new_to_the
           _facade, which re-creates the trigger in a real kernel; verified
           to fail on the old ordering.
       (T) `answers=[str(a) for a in …]` — a SearXNG answer is a dict
           {url, engine, parsed_url, template, answer}, so str() buried the
           one field worth reading under four rendering fields. Answers are
           the most valuable part of a search response (a direct answer beats
           ten links), so _answer() takes `answer`, and for the answer types
           that have no such key (Translations, WeatherAnswer — see
           searx/result_types/answer.py) emits JSON minus the boilerplate.
       (U) A blank query was accepted, and SearXNG answers one with a
           plugin's clock reading instead of an error: q="  " comes back with
           answers=[{"engine": "plugin: time_zone", "answer": "Sep 6, 2026,
           8:24:44 AM"}] and no hits. A nonsense success hides a caller bug,
           so target is stripped and a blank one raises.
       (V) The non-text error's own example leaked a client —
           `r = await httpx.AsyncClient().get(url)`, the exact shape of bug
           (a) this module exists to fix, being taught to the model in an
           error message. Now `async with`.
       (W) `_engine_down(["brave"])` returned "['brave']" — str() of the LIST
           on the no-reason branch, so a bare-name entry rendered as Python
           syntax in the one line that explains a degraded backend.
       Extraction: readabilipy's node mode is ~0.8s and visibly cleaner
       (3609 chars, no nav chrome, no raw <p> surviving markdownify) vs
       ~0.08s and 3466 chars with "Skip to main content" in it. So prefer
       node, fall back to pure Python, and DECIDE availability here —
       readabilipy's own have_node() spawns `node -v` per call and runs
       `npm install` when its node_modules is missing, and npm install chdirs
       the whole process. NOTE: the first live probe of extraction DID
       trigger that npm install (40 packages into
       .venv/…/readabilipy/javascript/node_modules). Benign and one-time —
       production would have done the same on first use — but it is exactly
       why _use_readability() exists, and node here is an fnm multishell
       path, so availability depends on the shell the server was launched
       from. Tests assert only what both modes agree on.
       Live: search 1.0-1.4s, fetch of a 43KB page 0.95s, an 11MB body
       refused in 17ms, gather of 3 searches 1.3x sequential (SearXNG itself
       is the bottleneck), a 132k-char page renders a 5098-char .text whose
       tail slice `markdown[5000:]` continues exactly where the window stops.
       Tests: 39 new in tests/unit/test_tools_web.py (hermetic — a local
       ThreadingHTTPServer stands in for both the web and SearXNG, real httpx
       and real readability, no mocks, no internet) + 1 drain test for
       `subject`. Sweep 689 -> 730 passed.
- [x] 8b. web run — playwright-python (USER RULED: playwright-python, not
       the playwright-cli skill, not selenium). Modes "run" and "close".
       * async_api ONLY. The sync API greenlet-switches into its own event
         loop (_sync_base.py: `self._loop.create_task` + dispatcher fiber)
         and a cell already runs inside ipykernel's running loop — the same
         wall that made pytest.main() need asyncio.to_thread.
       * Heavy, so LAZY: the wheel is 47MB because it bundles the Node
         driver (playwright-python is JSON-RPC to a node subprocess, not an
         FFI binding), plus `playwright install chromium` puts ~170MB in
         ~/.cache/ms-playwright. Optional extra + lazy import with a clear
         WebError, exactly how ast-grep is handled — a kernel that never
         browses never pays.
       * What the wrapper earns over "just use playwright in a cell":
         (1) LIFECYCLE — one browser/context/page for the kernel's lifetime
         instead of a 1s launch per cell and leaked processes;
         (2) EMISSION — a browser action becomes an ACP sibling call the
         client can watch, which plain playwright in a cell never does;
         (3) ARTIFACTS — a screenshot goes to the ImageStore and rides
         llm_images(), so a vision model can SEE the page. That third one is
         the real reason: bytes on disk are invisible to the model.
       * `.page` is exposed on the result, so clicking/typing/framing stays
         raw playwright in the kernel rather than a bad reimplementation of
         the playwright API. The tool does goto/evaluate/screenshot and then
         gets out of the way.
       * "run" returns the RENDERED page as the same PageResult shape fetch
         returns — that is the distinction a model cares about (static HTML
         vs. JS-executed DOM), and it means one result type for both.
       LANDED — playwright 1.62.0, and the probe found two more (letters
       continue the run):
       DEPENDENCY: HARD, not the optional extra the bullet above promised.
       The bullet's own reasoning is what overruled its wording: it said
       "exactly how ast-grep is handled", and ast-grep-py (43MB) and cv2
       (72MB) are both plain hard deps — there is no
       [project.optional-dependencies] table anywhere in this repo to be
       consistent with. An extra buys nothing here and costs a documented
       mode that cannot run: `web("run", …)` is in help() either way, so the
       only difference is whether the model gets a working browser or an
       install instruction. The 47MB wheel is the cheap half anyway — the
       ~170MB chromium is RUNTIME DATA in ~/.cache/ms-playwright, which no
       packaging scheme puts in a wheel. Lazy import stays, so a kernel that
       never browses never starts the node driver.
       Browser: 1.62 wants chromium-1234; the shared cache (3.3GB) had
       1012/1194/1217, so `uv --project . run playwright install chromium`
       — 114.7 MiB, one-time, into the shared cache. chromium-1234 and
       chromium_headless_shell-1234 now present.
       (X) THE SHARED-PAGE TRAP. The first cut kept ONE page for the
           kernel's lifetime, which made `r.page` a time bomb: a result from
           an earlier cell silently pointed at whatever the LATEST run had
           navigated to. Found live as a 30s timeout clicking a selector
           that was absent from the new page — and the worse version is a
           selector present on BOTH, which clicks the wrong thing and
           reports success. Fix: a FRESH page per run, previous page closed,
           so a stale `.page` raises playwright's TargetClosedError loudly
           instead of acting on the wrong document. The CONTEXT still
           survives (cookies/storage persist across runs), which is the part
           that actually needed to be shared.
       (Y) 404-AS-SUCCESS. `run` returned a 404 page as a completed
           PageResult while `fetch` raises on the same status — `.status`
           would have meant two different things in two modes of ONE tool.
           Now run raises WebError(f"{status} {status_text} for {url}") on
           >= 400. A browser renders an error page beautifully, which is
           exactly why the wrapper has to look at the number.
       Lifecycle handles live in `_state = globals().setdefault("_state",
       {})` + `_state.setdefault("lock", asyncio.Lock())` — a mutable CELL,
       not module globals, because importlib.reload re-executes the module
       source in the EXISTING module dict: a plain `_page = None` at module
       level would be re-assigned on every reload() and orphan a running
       chromium (and its node driver) with no way to reach it. setdefault
       makes the source line a no-op when the state already exists.
       One chromium + one context for the kernel's lifetime, started on the
       first run; `close` -> BrowserClosed(was_running) (new dataclass,
       result_kind "text", payload "browser closed" / "no browser was
       running"), idempotent, and a later run just starts a new one.
       Args: wait_until (playwright's four literals, default "load"),
       timeout (SECONDS, default 30, converted to ms — every other knob in
       this module speaks seconds), screenshot (default True). All three
       run-only and guarded; user_agent= stays fetch-only, limit=
       search-only, target= forbidden on close.
       REJECTED, with reasons (each was a real candidate):
       * `evaluate=` — `.page` is ambient; a JS return value is data the
         model handles better in Python than through a string parameter.
       * `full_page=` — with vision's 1568px cap a full-page shot of a long
         page is unreadable mush. The model scrolls and re-shoots.
       * `headless=` — a kernel is a server; there is no display to head
         toward and no user to watch the window.
       * `user_agent=` on run — the browser's own UA is the point of
         rendering; `r.page.context` is ambient for anyone who disagrees.
       Emission changed shape, and it corrects an 8a note: a browser call is
       ONE row carrying TWO artifacts (the rendered page as text AND the
       screenshot as an image), so image hydration is hoisted out of the
       drain's image branch into _hydrate_images(ctx, row, llm_blocks,
       store) and ANY row with llm_images now prepends hydrated image_url
       blocks — the else branch emits content=(text_blocks + image_blocks).
       And _KIND_BY_RESULT["web"] = "fetch" is now REQUIRED, contra 8a's
       "no _KIND_BY_RESULT entry is needed": that was true while the only
       web mode was named "fetch" (get_tool_kind matched on the MODE), but
       get_tool_kind("run") falls through to "other". A page is a fetch
       artifact whatever the mode is called. The 8a drain test's docstring
       claimed otherwise and was corrected.
       Screenshot reuses vision's _cap_resolution/_encode/_store, so the
       ImageStore keys dedupe with vision's — the same page shot twice is
       one blob.
       VERIFIED, not assumed:
       * Kernel reset takes the browser with it — after reset=True the node
         driver pid and all 7 chromium pids were gone (checked by pid with
         kill -0, because `pgrep -f` matches its own shell). No orphans, so
         no atexit hook.
       * The distinction the mode exists for, on one page: fetch -> title
         "Static Title", markdown "before"; run -> "Rendered Title",
         "built by JS".
       * Screenshot viewed with read_image_file: a real 1280x720 render
         (nav links, "The Heading", "Body one.", "Body two.");
         .screenshot.image -> PIL 1280x720 RGB.
       * Speed: driver start 0.28s, browser launch 0.05s, a full
         launch+goto+title+evaluate+screenshot+content+close 0.61s. First
         run 1.39s, warm 0.69s, gather of 3 runs 0.88s — serialized by the
         lock, each result correct with its own page.
       * Rows: run -> tool=web mode=run kind=web, llm_images=[{key, mime}],
         payload subject=<url>; close -> kind=text, "browser closed".
       * Guards all fire: 404, no-scheme, dead host (net::ERR_UNSAFE_PORT),
         timeout=0.5 on a 6s hang, bad wait_until, timeout<=0, run-only args
         on other modes, target= on close, and no-ImageStore (raises BEFORE
         launching a browser, message says screenshot=False).
       Tests: 39 -> 54 in tests/unit/test_tools_web.py — a module-scoped
       `chromium` fixture that launches once and pytest.skip's when the
       browser is missing (a 170MB download is not a test dependency), an
       autouse async _browser_down fixture (await MOD._shutdown() after
       every test), /js and /hang routes, 11 browser tests and 5 guard tests
       that need no browser. Plus 1 drain test for the two-artifact row.
       Sweep 730 -> 746 passed.
- [x] 9. memory — modes: list, search, sql (read-only conn -> polars
       DataFrame). Python objects, not LLM-markdown strings.
       LANDED — `crow_cli/tools/memory.py` (~700 lines, half of them the
       docstring that IS the schema documentation), MemoryResult +
       MemoryToolError + _compact in results.py, `register.db_uri()` as the
       rail accessor, `_KIND_BY_RESULT["memory"] = "read"`, and a pushdown
       fix in the memory package that the three MCP query tools inherit.
       DEPENDENCY: polars HARD (1.44.1) — meta wheel 0.9MB plus
       polars-runtime-32 58.6MB (55.8 MiB downloaded). The 8b ruling
       applies unchanged: ast-grep-py (43MB) and cv2 (72MB) are hard deps,
       there is no [project.optional-dependencies] table in this repo to be
       consistent with, and here the frame IS the result object — an extra
       would make `.df` a documented attribute that raises ImportError. The
       IMPORT stays lazy inside `_frame()` (measured 98ms, 43MB RSS) because
       reload() imports every _LAZY module at kernel start, so a module-level
       import would charge that to every kernel whether or not it ever reads
       memory.
       THE SHAPE. One tool, three modes, `ls` semantics for list: no
       session_id lists the database's entries (sessions, most-recently-active
       first, with msgs/agents/cwd/model and a 200-char last_text so a
       session is recognizable), session_id= lists THAT session's entries
       (its messages, oldest first). search is bm25, best-first. sql is the
       model's own statement, verbatim, over a read-only connection — and the
       function docstring carries the v5 schema plus four worked queries,
       because `help(memory)` is the just-in-time schema and a round trip to
       discover what `agents` holds costs a turn.
       Frames are EXACTLY eight columns each, and that is not a coincidence:
       polars' repr elides the middle of a wider frame (first four, last
       four), and print(r.df) is the LLM's entire view of the result. Eight
       columns means the repr shows every column, five rows from each end,
       ~30 chars a cell — a legible table of a 10,000-row result that cannot
       flood the context. That boundedness is why there is no windowing here
       (the _PAGE_WINDOW a page needs) and no pagination.
       `total` is computed where it is cheap (an indexed count for list) and
       NOT for search (a second expensive query; top-N is the point) nor sql
       (the statement is the whole answer). "50 of 2695" says raise the
       limit; "50" does not. Messages come back as the LAST N in
       CHRONOLOGICAL order (ORDER BY m.id DESC LIMIT, then rows.reverse()) —
       DESC+LIMIT is how you ask for a tail, and a transcript that arrives
       newest-first is wrong everywhere it is used. An unknown session_id
       RAISES: a typo and a session that said nothing look identical in an
       empty frame, and the first one is a caller bug. `roles` accepts a
       string (normalized to a 1-tuple, because a string is a sequence of
       characters, not of roles).
       THE PUSHDOWN FIX (memory/fts.py `search_rows`, reads.py
       `search_messages` now delegates to it). The old path fetched the
       GLOBAL top-80 and filtered in Python, so a session-scoped search for a
       common term returned the intersection of "best 80 in the database"
       with "in this session" — usually empty. Measured on this very session
       (global hits / in-session hits / what the OLD code returned):
       `config` 9614 / 199 / 3; `test` 16451 / 818 / 1; `the` 51986 / 1562 /
       1; `file` 15449 / 678 / 2; `prompt` 11644 / 141 / 0. The new path
       returns the true top-20 in 24–91ms. Dialect SQL stays in the seam
       (_SEARCH_ROWS: sqlite bm25(), postgres -ts_rank + plainto_tsquery),
       and it also deleted a load-the-whole-agents-table plus an
       overfetch-4x from reads.py. The sessions query is 4 statements
       (aggregate, count, one detail query, one row_number() window for the
       last message) replacing the MCP store's N+1. 103 tests in tests/memory
       + tests/mcp/test_memory*.py passed on the refactor before a line of
       the new tool existed.
       KILLED KNOBS — every one is a Python expression over the frame, which
       is the whole argument for returning a DataFrame instead of a string:
       mode=conversation|with_thinking|with_tools|full (a display filter for
       a transcript → `.filter()` on the role column), order=asc|desc
       (`.reverse()/.head()/.tail()`), offset (pagination dies wherever it
       appears), context=N (the frame carries the message `id`;
       list(session_id=…) carries the messages around it), after/before
       (created_at is a column of ISO strings, which compare
       lexicographically), search_type=semantic|keyword|both ("semantic" was
       bm25 all along and "keyword" was a substring scan in Python — sql does
       substring scans in sqlite's C, over columns FTS cannot see). KEPT:
       limit (top-N is a property of the QUERY), and roles / include_forks /
       session_id, which have to be INSIDE a ranked query for limit to mean
       "this many matches" rather than "this many rows scanned".
       Read-only at the CONNECTION level (get_ro_engine: sqlite mode=ro so
       the OS refuses, postgres READ ONLY characteristics so the server
       refuses). Verified live: insert/update/delete/create/drop all raise
       "attempt to write a readonly database"; `pragma journal_mode=wal` is a
       harmless no-op; ATTACH a fresh file and writing to it IS allowed — so
       the docstring says plainly that this is a guarantee about crow.db, not
       a sandbox (the kernel has write(), fs() and the filesystem anyway).
       The engine lives in `_state = globals().setdefault("_state", {})`
       keyed by uri, for the 8b reason: importlib.reload re-executes the
       source in the EXISTING module dict, so a module-level `_engine = None`
       would drop the handle on every reload() and leak its pool — fds on
       sqlite, a server session each on postgres. `_run` =
       asyncio.to_thread, for the vision/cv2 reason: a cell is already inside
       ipykernel's loop and a 500ms full scan on it stalls the kernel's
       heartbeats. QueuePool + 6 concurrent to_thread queries on one ro
       engine: no check_same_thread error.
       THE BYTE CAP STREAMS. `_fetch` iterates the result instead of
       fetchall() and breaks out of the loop, which stops sqlite stepping the
       query — measured on the live db: a 1MB cap on `select id, data from
       messages` returns 316 rows in 1ms where the same query aggregated to
       completion takes 511ms. That is what makes the 64MB cap a guard rather
       than a decoration: 499MB of message JSON never has to fit in the
       kernel to be refused. At the real cap, `select id, data from messages`
       over the live 1.3GB db returned 8567 rows, truncated=True, in 0.102s
       (RSS 242.9 → 286.7MB). The FIRST ROW IS ALWAYS KEPT, whatever it
       costs: one 12.8MB message (the live db's largest) must make a frame
       with one row in it, not an empty one that reads as "no matches".
       `truncated` is never silent, because a DataFrame that looks complete
       is indistinguishable from one that is.
       BUGS FOUND (letters continue the run):
       (Z) `lim` BINDPARAM REUSE. _q_messages built one params dict and
           reused it for the count statement, which has no `:lim` →
           "This text() construct doesn't define a bound parameter named
           'lim'". The count uses params, the paged query
           {**params, "lim": limit}.
       (AA) `roles=` SILENTLY IGNORED on a sessions list — an argument the
           caller cared about, quietly dropped, which is the (U)-class bug
           from 6d. A sessions list has no role column to filter, so it now
           raises and names the fix (pass session_id=).
       (AB) A FALSE CLAIM, written then disproved: I asserted text() would
           break on a colon inside a string literal. Tested — text() handles
           '%a:b%', `-- why: because` and `/* note: x */` fine (it skips
           quoted literals and comments). The real difference, and the reason
           sql mode uses exec_driver_sql, is WHO COMPLAINS: on
           `where role = :role`, text() blames SQLAlchemy ("A value is
           required for bind parameter 'role'") while the driver lets the
           database speak ("Incorrect number of bindings supplied"). This
           mode's contract is that what you wrote is what runs, so the
           database should be the one to say what is wrong with it. Both
           messages are pinned by tests.
       (AC) A SECOND FALSE CLAIM, this one about _compact: the docstring said
           a full ISO stamp is three wrapped repr lines and ten rows print as
           36 lines instead of 16. Measured across width budgets on a 10-row
           messages frame: 27 → 17 lines at 150 chars, and NO CHANGE at 100
           (both wrap; the row height is set by the tallest cell, which is
           `calls`) or at 200 (both fit). So the honest justification is
           noise, not height — a full stamp spends its column's width on
           microseconds and an offset nobody can use, rendering as
           `2026-09-06T10` / `:17:44.233789` / `+00:…` where the readable
           content is the same 19 characters. Kept (it never costs height,
           .df stays lossless and its ISO strings still compare
           lexicographically), docstring rewritten to the measurement, and
           the test pins the trim rather than a line count that only exists
           at one width.
       (AD) A THIRD FALSE CLAIM, about _cell: I had recorded "polars Struct
           inference RAISES on heterogeneous dicts". Measured on 1.44.1, it
           does not — it infers the Struct from the FIRST row and SILENTLY
           DROPS every key that row lacked (`tool_calls` vanishes, no error),
           and raises TypeError only when the same key changes TYPE, which is
           the shape a real messages table actually has (content is a str in
           a user row and a list of blocks in an assistant one). The silent
           loss is worse than the raise, so _cell stands on stronger evidence
           than it had — but the docstring said the wrong thing, and a test
           now pins both behaviours.
       LIVE MEASUREMENTS (crow.db, 1274.3MB): 83,241 → 83,355 messages, 2,899
       agents, 2,695 sessions; roles tool 35,107 / assistant 34,536 / user
       10,713 / system 2,885; `data` averages 6.0KB, max 12.8MB, 499.3MB
       total. list 50 of 2695 sessions in 0.236s (500 in 0.569s); the biggest
       session (caped-academic-fulmar-of-endurance, 6716 msgs / 32.3MB) at
       the default limit=1000 in 0.258s, and limit=10000 → all 6716 rows
       (25.6MB of text) in 0.401s with an RSS peak of 409.6MB. Every guard
       was fired live before the tests were written: bad mode, missing/blank
       target on sql and search, target on list, each of the four forbidden
       sql args, bad role, roles as a str, roles without session_id, negative
       limit, limit 99999, unknown session, blank session_id, bad SQL
       (`near "selct": syntax error`), a write attempt, no such table, no
       rail, a missing db file, engine caching and rebuild-on-uri-change,
       include_forks on search (0 trunk vs 1 fork at fork_idx=2), limit=0,
       and the register row (kind memory, subject polars).
       TESTS: 56 in tests/unit/test_tools_memory.py (no mocks — a real crow.db
       built through create_database/create_agent/add_message so the FTS
       index is the one the product maintains, read through the real
       read-only engine; timestamps stamped explicitly because
       most-recently-active is the sort under test and now_iso() would hand
       it to the clock), + 1 drain test (all three modes file under kind
       "read" via _KIND_BY_RESULT, subject rides the title, locations stays
       None because a frame of rows is not a file) + 1 real-kernel test in
       test_execute_prelude.py (memory is ambient on start, reads the db the
       prologue injected, the cached engine survives a mid-cell reload(), and
       the three calls write through into the SAME database the tool was
       reading — ro engine and rw sink coexisting on one file).
       Sweep 746 -> 804 passed (136s, -p no:randomly).
- [ ] 9b. THE INDEX HOLE — messages_fts indexes message_text(), which is
       content + reasoning_content and NOT tool_calls. Measured on the live
       db: 29,499 assistant rows carry tool_calls and 17,208 of them have
       empty content, so bm25 cannot see them AT ALL — 21% of the database.
       For the path `crow-cli-jupyter/EXECUTE_TODO.md`: 121 messages contain
       it in `data` (assistant 70, tool 50, user 2) but FTS finds 53
       (assistant 1, tool 50, user 2) — the 69 missing ones mention it only
       inside an edit's arguments. Tool RESULTS are indexed (a tool message's
       content is the result), which is why the hole is easy to miss: a
       search for a file you edited returns the result rows and looks like it
       works. memory's docstring documents the hole and the workaround
       (`sql` with `data LIKE '%…%'`, a 0.5s full scan over 499MB that sees
       everything), and two tests pin both sides of it.
       THE FIX IS NOT WRITTEN because it mutates the user's real memory:
       message_text() would have to render tool_calls into the searchable
       text (name + arguments, probably truncated), and then a reindex script
       has to rewrite 83k rows of messages_fts over a 1.3GB live database —
       plus the same change on the postgres side, where the tsvector is
       maintained from Python in the insert transaction. Per "propose a new
       plan and confirm with the user before proceeding" on anything that
       touches real data, the measurements are recorded here for the plan
       person to rule on. Open questions for that ruling: does an edit's
       arguments belong in a KEYWORD index at all (they are JSON, and
       bm25-ranking a blob of escaped quotes will surface it above prose for
       almost any query), or is the honest answer a separate
       `tool_calls_text` column indexed with its own weight, or no index and
       a documented LIKE scan?
- [ ] 9c. PRE-EXISTING FLAKE, found by the step-9 sweep and NOT caused by it:
       tests/integration/test_cancel_under_load.py HANGS (no failure, no
       output, forever) roughly one run in six. Reproduced 3× with step 9 in
       the tree and 1× in 8 runs with every step-9 source change stashed away
       at 5ff2bcac, so it predates this work; it also hangs when that file is
       the ONLY thing collected, so it is not an interaction with tests/unit.
       Shape of the hang: `-v -s` shows the previous test's PASSED and then
       nothing, and the next item's name is never printed — pytest prints the
       name in pytest_runtest_logstart, before setup, so the hang is in the
       TEARDOWN of the test that just passed, i.e. exiting
       `async with app.run_test(size=(120, 40))` after a stream was
       cancelled mid-flight (the mock agent / ACP connection / Textual app
       not always shutting down). It cost a 1500s sweep timeout and makes the
       full-sweep gate unreliable, which is why it is on the list rather than
       in a footnote: a gate that flakes 1-in-6 gets re-run until it passes,
       and that is how a real regression walks through.

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
  engine, crow_cli.memory) are NOT covered by reload() — verified live, not
  reasoned: fixing `_resolve_path` in crow_cli.mcp.editor.main and calling
  `reload()` still showed the old behaviour, because fs re-imports the
  function object from the already-loaded module. Reload that module
  explicitly first (`importlib.reload(sys.modules["crow_cli.mcp.editor.
  main"])`, then `reload()`), or reset the kernel if the dependency chain is
  deep. Three traps it handles:
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

## Decided — the four simplification candidates (settled, not pending)

Ruled on by the plan-personified: "do that" = delete #2, keep #1 for now,
keep #3 and #4 as recommended, and ratify all four deviations (the three in
6b plus glob-is-ripgrep-not-pathspec in 6a).

1. `register._entries` / `pending()` / `drain()` — KEPT FOR NOW, deleted in
   step 13 (the endgame) when the test suite is rewritten anyway. They are
   dead in production: the DB table is the queue (write-through at call
   time, the server drains by parent tcid), and the in-kernel list is a
   second source of truth that only kernel-local tests read
   (tests/mcp/test_execute_prelude.py asserts on `drain()`,
   tests/unit/test_tools_*.py on `pending()`). Deleting it today buys
   cleanliness and costs a dozen rewritten assertions; deleting it in 13
   costs nothing extra. DO NOT FORGET IT — it is the only item here with a
   future action attached.
2. The drain's `content == "multi-diff"` branch — DELETED, along with
   `_subtool_id`'s `part` argument. Nothing produced it once 6b chose
   per-file write rows, and the rewrite proved N rows is the better shape:
   the bytes land where the diffs already live instead of megabytes of
   whole files going into one row. One row, one call.
3. `acp_payload()` — KEPT. Redundant for the diff tools (the drain needs
   exactly EditResult's fields), but it is what keeps crow_cli.tools
   acp-free, and it is the seam a new artifact type plugs into — image and
   read results both work through it.
4. `_emit_subtool_call`'s three beats (pending / in_progress / completed) —
   KEPT at three where two would do: byte-for-byte the shape crow sends for
   a real edit call, and the client merges them.
