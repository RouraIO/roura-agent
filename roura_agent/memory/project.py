"""
Roura Agent Project Memory - Per-project memory scoping.

Provides:
- Project-scoped memory isolation
- Global vs project-local preferences
- Memory inheritance and sharing
- Project detection and identification

© Roura.io
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from ..logging import get_logger
from .consent import ConsentManager, MemoryType, get_consent_manager
from .encryption import EncryptedStore, get_or_create_store

logger = get_logger(__name__)


@dataclass
class ProjectScope:
    """
    Identifies a project for memory scoping.

    Projects are identified by their root directory path.
    A unique ID is generated from the path for storage.
    """
    root_path: Path
    name: Optional[str] = None
    project_id: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def __post_init__(self):
        self.root_path = Path(self.root_path).resolve()
        if not self.name:
            self.name = self.root_path.name
        if not self.project_id:
            self.project_id = self._generate_id()

    def _generate_id(self) -> str:
        """Generate unique ID from path."""
        path_str = str(self.root_path)
        return hashlib.sha256(path_str.encode()).hexdigest()[:16]

    @property
    def memory_dir(self) -> Path:
        """Get the .roura directory for this project."""
        return self.root_path / ".roura"

    @property
    def memory_file(self) -> Path:
        """Get the memory file path."""
        return self.memory_dir / "memory.json"

    @property
    def encrypted_memory_file(self) -> Path:
        """Get the encrypted memory file path."""
        return self.memory_dir / "memory.enc"

    def exists(self) -> bool:
        """Check if project root exists."""
        return self.root_path.exists()

    def has_memory(self) -> bool:
        """Check if project has memory stored."""
        return self.memory_file.exists() or self.encrypted_memory_file.exists()

    def to_dict(self) -> dict:
        return {
            "root_path": str(self.root_path),
            "name": self.name,
            "project_id": self.project_id,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ProjectScope":
        return cls(
            root_path=Path(data["root_path"]),
            name=data.get("name"),
            project_id=data.get("project_id"),
            created_at=data.get("created_at", ""),
        )

    @classmethod
    def detect(cls, start_path: Optional[Path] = None) -> Optional["ProjectScope"]:
        """
        Detect project root from current or given path.

        Looks for common project markers like .git, pyproject.toml, etc.

        Args:
            start_path: Starting path (default: cwd)

        Returns:
            ProjectScope or None if not in a project
        """
        path = (start_path or Path.cwd()).resolve()

        markers = [
            ".git",
            ".roura",
            "pyproject.toml",
            "package.json",
            "Cargo.toml",
            "go.mod",
            ".project",
            "Makefile",
        ]

        # Walk up directory tree
        while path != path.parent:
            for marker in markers:
                if (path / marker).exists():
                    return cls(root_path=path)
            path = path.parent

        return None


@dataclass
class ProjectMemoryEntry:
    """A single memory entry with metadata."""
    content: str
    category: str  # e.g., "note", "fact", "preference", "context"
    tags: list[str] = field(default_factory=list)
    source: str = "user"  # "user", "agent", "system"
    relevance: float = 1.0  # 0.0 to 1.0
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: Optional[str] = None
    entry_id: str = field(default_factory=lambda: __import__("secrets").token_hex(8))

    def to_dict(self) -> dict:
        return {
            "content": self.content,
            "category": self.category,
            "tags": self.tags,
            "source": self.source,
            "relevance": self.relevance,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "entry_id": self.entry_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ProjectMemoryEntry":
        return cls(
            content=data["content"],
            category=data.get("category", "note"),
            tags=data.get("tags", []),
            source=data.get("source", "user"),
            relevance=data.get("relevance", 1.0),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at"),
            entry_id=data.get("entry_id", ""),
        )


class ProjectMemory:
    """
    Per-project memory storage with encryption support.

    Provides:
    - Project-scoped memory isolation
    - Encrypted storage option
    - Consent-aware access
    - Category-based organization
    """

    def __init__(
        self,
        scope: Optional[ProjectScope] = None,
        encrypted: bool = False,
        consent_manager: Optional[ConsentManager] = None,
        *,
        root: Optional[Path] = None,  # Backward compatibility
        require_consent: Optional[bool] = None,  # None = auto-detect
    ):
        # Backward compatibility: accept root= keyword argument
        # When using root=, skip consent checks for compatibility
        self._legacy_mode = root is not None and scope is None
        if self._legacy_mode:
            scope = ProjectScope(root_path=root)
        elif scope is None:
            raise ValueError("Either 'scope' or 'root' must be provided")

        self.scope = scope
        self.encrypted = encrypted
        self._consent = consent_manager or get_consent_manager()
        self._entries: list[ProjectMemoryEntry] = []
        self._preferences: dict[str, Any] = {}
        self._loaded = False

        # Auto-detect consent requirement based on mode
        if require_consent is None:
            self._require_consent = not self._legacy_mode
        else:
            self._require_consent = require_consent

        # Encryption store (lazy initialized)
        self._store: Optional[EncryptedStore] = None

    def _get_store(self) -> EncryptedStore:
        """Get or create encryption store."""
        if self._store is None:
            self._store = get_or_create_store()
        return self._store

    def _check_consent(self, memory_type: MemoryType) -> bool:
        """Check if operation is allowed by consent."""
        if not self._require_consent:
            return True  # Skip consent check in legacy mode
        return self._consent.check_consent(memory_type)

    def load(self) -> bool:
        """
        Load memory from storage.

        Returns:
            True if loaded successfully
        """
        if self._loaded:
            return True

        if not self._check_consent(MemoryType.PROJECT_NOTES):
            logger.debug("Memory access denied by consent")
            return False

        try:
            if self.encrypted and self.scope.encrypted_memory_file.exists():
                data = self._get_store().load_encrypted(self.scope.encrypted_memory_file)
            elif self.scope.memory_file.exists():
                data = json.loads(self.scope.memory_file.read_text())
            else:
                self._loaded = True
                return True  # No existing memory

            self._entries = [
                ProjectMemoryEntry.from_dict(e)
                for e in data.get("entries", [])
            ]
            self._preferences = data.get("preferences", {})
            self._loaded = True
            return True

        except Exception as e:
            logger.error(f"Failed to load project memory: {e}")
            return False

    def save(self) -> bool:
        """
        Save memory to storage.

        Returns:
            True if saved successfully
        """
        if not self._check_consent(MemoryType.PROJECT_NOTES):
            logger.debug("Memory save denied by consent")
            return False

        try:
            # Ensure directory exists
            self.scope.memory_dir.mkdir(parents=True, exist_ok=True)

            if self._legacy_mode:
                # Legacy format compatible with persistent.py
                data = {
                    "version": 1,
                    "notes": [
                        {
                            "content": e.content,
                            "created_at": e.created_at,
                            "tags": e.tags,
                            "source": e.source,
                        }
                        for e in self._entries
                    ],
                    "sessions": [],
                    "preferences": self._preferences,
                }
            else:
                # New v2.5 format
                data = {
                    "version": 2,
                    "project_id": self.scope.project_id,
                    "entries": [e.to_dict() for e in self._entries],
                    "preferences": self._preferences,
                    "updated_at": datetime.now().isoformat(),
                }

            if self.encrypted:
                self._get_store().save_encrypted(
                    self.scope.encrypted_memory_file,
                    data,
                )
            else:
                self.scope.memory_file.write_text(json.dumps(data, indent=2))

            return True

        except Exception as e:
            logger.error(f"Failed to save project memory: {e}")
            return False

    def add(
        self,
        content: str,
        category: str = "note",
        tags: Optional[list[str]] = None,
        source: str = "user",
        relevance: float = 1.0,
    ) -> Optional[ProjectMemoryEntry]:
        """
        Add a memory entry.

        Args:
            content: Entry content
            category: Category (note, fact, preference, context)
            tags: Optional tags
            source: Source (user, agent, system)
            relevance: Relevance score 0-1

        Returns:
            Created entry or None if denied
        """
        memory_type = MemoryType.AGENT_NOTES if source == "agent" else MemoryType.PROJECT_NOTES
        if not self._check_consent(memory_type):
            return None

        if not self._loaded:
            self.load()

        entry = ProjectMemoryEntry(
            content=content,
            category=category,
            tags=tags or [],
            source=source,
            relevance=relevance,
        )
        self._entries.append(entry)
        return entry

    def get(self, entry_id: str) -> Optional[ProjectMemoryEntry]:
        """Get entry by ID."""
        if not self._loaded:
            self.load()

        for entry in self._entries:
            if entry.entry_id == entry_id:
                return entry
        return None

    def remove(self, entry_id: str) -> bool:
        """Remove entry by ID."""
        if not self._loaded:
            self.load()

        for i, entry in enumerate(self._entries):
            if entry.entry_id == entry_id:
                del self._entries[i]
                return True
        return False

    def search(
        self,
        query: str,
        category: Optional[str] = None,
        tags: Optional[list[str]] = None,
        min_relevance: float = 0.0,
        limit: int = 10,
    ) -> list[ProjectMemoryEntry]:
        """
        Search memory entries.

        Args:
            query: Search query
            category: Filter by category
            tags: Filter by tags
            min_relevance: Minimum relevance score
            limit: Maximum results

        Returns:
            Matching entries
        """
        if not self._loaded:
            self.load()

        query_lower = query.lower()
        results = []

        for entry in self._entries:
            # Relevance filter
            if entry.relevance < min_relevance:
                continue

            # Category filter
            if category and entry.category != category:
                continue

            # Tags filter
            if tags and not any(t in entry.tags for t in tags):
                continue

            # Content match
            if query_lower in entry.content.lower():
                results.append(entry)

        # Sort by relevance
        results.sort(key=lambda e: e.relevance, reverse=True)
        return results[:limit]

    def get_by_category(self, category: str) -> list[ProjectMemoryEntry]:
        """Get all entries in a category."""
        if not self._loaded:
            self.load()
        return [e for e in self._entries if e.category == category]

    def get_by_tags(self, tags: list[str]) -> list[ProjectMemoryEntry]:
        """Get entries with any of the given tags."""
        if not self._loaded:
            self.load()
        return [e for e in self._entries if any(t in e.tags for t in tags)]

    def set_preference(self, key: str, value: Any) -> None:
        """Set a project preference."""
        if not self._check_consent(MemoryType.PREFERENCES):
            return
        if not self._loaded:
            self.load()
        self._preferences[key] = value

    def get_preference(self, key: str, default: Any = None) -> Any:
        """Get a project preference."""
        if not self._loaded:
            self.load()
        return self._preferences.get(key, default)

    def to_context(self, max_entries: int = 10, max_chars: int = 2000) -> str:
        """
        Generate context string for LLM injection.

        Args:
            max_entries: Maximum entries to include
            max_chars: Maximum total characters

        Returns:
            Formatted context string
        """
        if not self._loaded:
            self.load()

        if not self._entries:
            return ""

        # Sort by relevance
        sorted_entries = sorted(self._entries, key=lambda e: e.relevance, reverse=True)

        parts = [f"## Project Memory ({self.scope.name})"]
        total_chars = 0

        for entry in sorted_entries[:max_entries]:
            line = f"- [{entry.category}] {entry.content}"
            if entry.tags:
                line += f" (tags: {', '.join(entry.tags)})"

            if total_chars + len(line) > max_chars:
                break

            parts.append(line)
            total_chars += len(line)

        return "\n".join(parts)

    def clear(self, category: Optional[str] = None) -> int:
        """
        Clear memory entries.

        Args:
            category: Optional category to clear (all if None)

        Returns:
            Number of entries cleared
        """
        if not self._loaded:
            self.load()

        if category:
            original = len(self._entries)
            self._entries = [e for e in self._entries if e.category != category]
            return original - len(self._entries)
        else:
            count = len(self._entries)
            self._entries.clear()
            return count

    def __len__(self) -> int:
        if not self._loaded:
            self.load()
        return len(self._entries)

    # =========================================================================
    # Backward compatibility with legacy ProjectMemory API
    # =========================================================================

    @property
    def notes(self) -> list:
        """
        Backward compatibility: return entries as note-like objects.

        Returns list with content/tags/source/created_at attributes.
        """
        if not self._loaded:
            self.load()
        return self._entries

    @notes.setter
    def notes(self, value: list) -> None:
        """Backward compatibility: set notes from list."""
        self._entries = value
        self._loaded = True

    def add_note(
        self,
        content: str,
        tags: Optional[list[str]] = None,
        source: str = "user",
    ) -> Optional[ProjectMemoryEntry]:
        """
        Backward compatibility: add a note.

        Wraps the add() method with category="note".
        """
        return self.add(
            content=content,
            category="note",
            tags=tags,
            source=source,
        )


# Global project memory cache
_project_memories: dict[str, ProjectMemory] = {}


def get_project_memory(
    path: Optional[Path] = None,
    encrypted: bool = False,
) -> Optional[ProjectMemory]:
    """
    Get project memory for the given or current path.

    Args:
        path: Project path (default: cwd)
        encrypted: Whether to use encryption

    Returns:
        ProjectMemory or None if not in a project
    """
    scope = ProjectScope.detect(path)
    if not scope:
        return None

    # Check cache
    cache_key = f"{scope.project_id}:{encrypted}"
    if cache_key in _project_memories:
        return _project_memories[cache_key]

    # Create new
    memory = ProjectMemory(scope, encrypted=encrypted)
    memory.load()
    _project_memories[cache_key] = memory
    return memory


def clear_project_memory_cache() -> None:
    """Clear the project memory cache."""
    global _project_memories
    _project_memories.clear()
