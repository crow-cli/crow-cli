# RULES

- Never mention the user's emotional state. I'm here to work, NOT be psychoanalyzed by a machine.

# MEMORY FOOTPRINT (MCP server)

Long-lived server RSS is an ALLOCATOR HIGH-WATER MARK, not a live count:
Python frees objects, glibc/mimalloc keep the pages. Any large transient
ratchets the peak permanently unless trimmed.

- `query_session` / `list_sessions` materialize FULL sessions before slicing
  in Python (`src/crow_cli/mcp/memory/main.py` -> store.session_records ->
  `cm.query_messages(limit=1_000_000)`). Biggest sessions are 30+ MB each.
  Same bug class was fixed for list_sessions in 18ecf528 (0.1.37).
- Fix shipped: `MemoryTrimMiddleware` (src/crow_cli/mcp/server/memtrim.py),
  every 10 requests `gc.collect()` + `malloc_trim(0)`. Verified live: RSS
  snaps back to a stable plateau after heavy sessions disconnect; NO
  per-cycle accumulation. malloc_trim cannot free pages while the MCP
  session holding them is still open — the drop happens at the first trim
  AFTER disconnect. That is expected, not a bug.
- CPython 3.14 here uses mimalloc for objects; malloc_trim only touches the
  glibc brk heap. Both layers matter; MIMALLOC_PURGE_DECOMMITS not needed.
- Diagnosis toolkit that worked: /proc/PID/status VmRSS sampler, smaps
  analysis (heap vs anon), gc census via gc.get_objects() type counts,
  weakref.finalize sentinels to prove collection. py-spy attach is blocked
  (ptrace_scope=1, no sudo) — use repro servers on a spare port with
  CROW_DB_URI pointing at a sqlite backup instead.
