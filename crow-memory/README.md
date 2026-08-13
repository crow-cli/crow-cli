# crow-memory

The one memory contract for crow. SQLAlchemy over a caller-supplied `db_uri`
— sqlite by default, postgres a seam away. Shared by **crow-cli** (writes)
and **crow-mcp** (read-only queries).

```python
import crow_memory

uri = crow_memory.normalize_db_uri("~/.agents/crow/crow.db")  # or postgresql://...
crow_memory.create_database(uri)          # tables + FTS5 index (sqlite)
engine = crow_memory.get_engine(uri)

crow_memory.create_agent(engine, agent_id="s-1", session_id="s", agent_idx=1)
crow_memory.add_message(engine, "s-1", {"role": "user", "content": "hi"})
crow_memory.search_messages(engine, "hi")  # FTS5 bm25 (sqlite)
```

Design rules:

- **No config in this package.** Apps resolve their own `db_uri` and pass it
  in. `normalize_db_uri` accepts a full URI or a plain path.
- Images never live in the DB: `add_message(..., images_dir=)` extracts
  inline base64 to content-addressed files; `load_messages(..., hydrate=True)`
  swaps refs back to data URLs.
- Read-only consumers (crow-mcp) use
  `get_engine("sqlite:///file:<path>?mode=ro&uri=true")`.
- Keyword search is SQLite FTS5. A future postgres backend needs its own
  search implementation behind `search_messages`; everything else is
  portable SQLAlchemy already.

Tests: `uv --project . run pytest`
