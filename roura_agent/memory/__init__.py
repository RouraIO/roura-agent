"""
Roura Agent Memory - Persistent project memory and session history.

Provides:
- Persistent note storage
- Session summaries
- Semantic search (TF-IDF based)
- RAG-ready context retrieval

© Roura.io
"""
from .persistent import (
    MemoryNote,
    MemorySearchIndex,
    ProjectMemory,
    RAGMemory,
    # RAG / Search
    SearchResult,
    SessionSummary,
    get_memory,
    tokenize,
)

__all__ = [
    # Core
    "ProjectMemory",
    "MemoryNote",
    "SessionSummary",
    "get_memory",
    # RAG / Search
    "SearchResult",
    "MemorySearchIndex",
    "RAGMemory",
    "tokenize",
]
