"""
Roura Agent Memory - Persistent project memory and session history.

Provides:
- Persistent note storage
- Session summaries
- Semantic search (TF-IDF based)
- RAG-ready context retrieval
- Encrypted storage (v2.5)
- Consent management (v2.5)
- Per-project scoping (v2.5)

© Roura.io
"""
# Legacy persistent memory
from .persistent import (
    MemoryNote,
    MemorySearchIndex,
    ProjectMemory as LegacyProjectMemory,
    RAGMemory,
    SearchResult,
    SessionSummary,
    get_memory,
    tokenize,
)

# v2.5: Encryption
from .encryption import (
    EncryptionKey,
    EncryptedStore,
    generate_key,
    derive_key,
    get_or_create_store,
    CRYPTO_AVAILABLE,
)

# v2.5: Consent management
from .consent import (
    ConsentStatus,
    ConsentRecord,
    ConsentPreferences,
    ConsentManager,
    MemoryType,
    get_consent_manager,
    check_memory_consent,
    require_memory_consent,
)

# v2.5: Per-project scoping
from .project import (
    ProjectScope,
    ProjectMemoryEntry,
    ProjectMemory,
    get_project_memory,
    clear_project_memory_cache,
)

__all__ = [
    # Legacy Core
    "LegacyProjectMemory",
    "MemoryNote",
    "SessionSummary",
    "get_memory",
    # RAG / Search
    "SearchResult",
    "MemorySearchIndex",
    "RAGMemory",
    "tokenize",
    # v2.5: Encryption
    "EncryptionKey",
    "EncryptedStore",
    "generate_key",
    "derive_key",
    "get_or_create_store",
    "CRYPTO_AVAILABLE",
    # v2.5: Consent
    "ConsentStatus",
    "ConsentRecord",
    "ConsentPreferences",
    "ConsentManager",
    "MemoryType",
    "get_consent_manager",
    "check_memory_consent",
    "require_memory_consent",
    # v2.5: Project Scoping
    "ProjectScope",
    "ProjectMemoryEntry",
    "ProjectMemory",
    "get_project_memory",
    "clear_project_memory_cache",
]
