# crow-memory-sdk (Python)

Async Python client for the **crow-memory** HTTP service — the LanceDB-backed
agent memory that lives at `http://127.0.0.1:27697` by default. Mirrors the
Rust `crow-memory-sdk` crate endpoint-for-endpoint.

```python
from crow_memory_sdk import MemoryClient

async with MemoryClient() as mem:
    await mem.health()
    sessions = await mem.list_sessions(limit=10)
    hits = await mem.search_messages("daemon EADDRINUSE", limit=5)
```

- `CROW_MEMORY_URL` overrides the base URL.
- Retry policy: connect errors + 502/503/504 back off exponentially (3 tries);
  every other error fails fast.
- Append-only service: create + read/search. No update, no delete.
