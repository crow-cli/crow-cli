"""crow-memory: LanceDB-backed memory for Crow.

Dual tables (messages + images), two resident multivector embedders
(ColBERT for text, ColQwen2/ColPali for images), unified MaxSim search.

Used in-process by crow-cli and crow-mcp — no service, no HTTP.
"""

__version__ = "0.1.29"

_store = None


def get_store(path: str | None = None):
    """Process-wide singleton MemoryStore. Lazy-loads embedders on first call."""
    global _store
    if _store is None:
        from pathlib import Path
        from .embed import Embedders
        from .store import MemoryStore

        path = path or str(Path.home() / ".crow" / "memory.lance")
        _store = MemoryStore(path, Embedders())
    return _store
