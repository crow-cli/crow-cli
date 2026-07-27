"""crow-memory: LanceDB-backed memory service for Crow.

Dual tables (messages + images), two resident multivector embedders
(ColBERT for text, ColQwen2/ColPali for images), unified MaxSim search.
Replaces crow-cli's SQLAlchemy persistence and crow-mcp's query_memory.
"""

__version__ = "0.1.26"
