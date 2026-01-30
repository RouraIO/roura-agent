"""
Roura Agent Persistent Memory - Project memory stored in .roura directory.

Provides:
- Persistent note storage
- Session summaries
- Semantic search (keyword-based with optional embeddings)
- RAG-ready retrieval

© Roura.io
"""
from __future__ import annotations

import json
import re
import math
import logging
from collections import Counter
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


@dataclass
class MemoryNote:
    """A persistent note about the project."""
    content: str
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    tags: list[str] = field(default_factory=list)
    source: str = "user"  # "user" or "agent"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "MemoryNote":
        return cls(**data)


@dataclass
class SessionSummary:
    """Summary of a past session."""
    summary: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    files_touched: list[str] = field(default_factory=list)
    tools_used: list[str] = field(default_factory=list)
    duration_seconds: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "SessionSummary":
        return cls(**data)


@dataclass
class ProjectMemory:
    """
    Persistent memory for a project.

    Stores notes, session summaries, and preferences in .roura/memory.json.

    Usage:
        memory = ProjectMemory.load("/path/to/project")
        memory.add_note("This project uses pytest for testing")
        memory.save()
    """

    # Project root directory
    root: Path

    # Memory data
    notes: list[MemoryNote] = field(default_factory=list)
    sessions: list[SessionSummary] = field(default_factory=list)
    preferences: dict[str, Any] = field(default_factory=dict)

    # Limits
    max_notes: int = 100
    max_sessions: int = 50

    @property
    def memory_dir(self) -> Path:
        """Get the .roura directory path."""
        return self.root / ".roura"

    @property
    def memory_file(self) -> Path:
        """Get the memory.json file path."""
        return self.memory_dir / "memory.json"

    def add_note(
        self,
        content: str,
        tags: Optional[list[str]] = None,
        source: str = "user",
    ) -> None:
        """
        Add a note to memory.

        Args:
            content: The note content
            tags: Optional tags for categorization
            source: "user" if user-provided, "agent" if agent-generated
        """
        note = MemoryNote(
            content=content,
            tags=tags or [],
            source=source,
        )
        self.notes.append(note)

        # Trim if over limit (keep most recent)
        if len(self.notes) > self.max_notes:
            self.notes = self.notes[-self.max_notes:]

    def add_session(
        self,
        summary: str,
        files_touched: Optional[list[str]] = None,
        tools_used: Optional[list[str]] = None,
        duration_seconds: int = 0,
    ) -> None:
        """
        Add a session summary to memory.

        Args:
            summary: Brief summary of what was done
            files_touched: List of files that were modified
            tools_used: List of tools that were used
            duration_seconds: How long the session lasted
        """
        session = SessionSummary(
            summary=summary,
            files_touched=files_touched or [],
            tools_used=tools_used or [],
            duration_seconds=duration_seconds,
        )
        self.sessions.append(session)

        # Trim if over limit (keep most recent)
        if len(self.sessions) > self.max_sessions:
            self.sessions = self.sessions[-self.max_sessions:]

    def set_preference(self, key: str, value: Any) -> None:
        """Set a project preference."""
        self.preferences[key] = value

    def get_preference(self, key: str, default: Any = None) -> Any:
        """Get a project preference."""
        return self.preferences.get(key, default)

    def get_notes_by_tag(self, tag: str) -> list[MemoryNote]:
        """Get notes with a specific tag."""
        return [n for n in self.notes if tag in n.tags]

    def get_recent_sessions(self, count: int = 5) -> list[SessionSummary]:
        """Get the most recent session summaries."""
        return self.sessions[-count:]

    def to_context_prompt(self) -> str:
        """
        Generate a context string for injection into system prompt.

        Returns:
            String with relevant memory for the LLM
        """
        parts = []

        # Add notes (most relevant)
        if self.notes:
            parts.append("## Project Notes")
            for note in self.notes[-10:]:  # Last 10 notes
                tags = f" [{', '.join(note.tags)}]" if note.tags else ""
                parts.append(f"- {note.content}{tags}")

        # Add recent session summaries
        recent = self.get_recent_sessions(3)
        if recent:
            parts.append("\n## Recent Sessions")
            for session in recent:
                date = session.timestamp.split("T")[0]
                parts.append(f"- {date}: {session.summary}")

        # Add relevant preferences
        if self.preferences:
            parts.append("\n## Preferences")
            for key, value in self.preferences.items():
                parts.append(f"- {key}: {value}")

        return "\n".join(parts) if parts else ""

    def save(self) -> None:
        """Save memory to disk."""
        # Ensure directory exists
        self.memory_dir.mkdir(parents=True, exist_ok=True)

        data = {
            "version": 1,
            "notes": [n.to_dict() for n in self.notes],
            "sessions": [s.to_dict() for s in self.sessions],
            "preferences": self.preferences,
        }

        with open(self.memory_file, "w") as f:
            json.dump(data, f, indent=2)

    @classmethod
    def load(cls, root: str | Path) -> "ProjectMemory":
        """
        Load memory from disk or create new.

        Args:
            root: Project root directory

        Returns:
            ProjectMemory instance
        """
        root = Path(root).resolve()
        memory = cls(root=root)

        memory_file = memory.memory_file
        if memory_file.exists():
            try:
                with open(memory_file, "r") as f:
                    data = json.load(f)

                memory.notes = [
                    MemoryNote.from_dict(n)
                    for n in data.get("notes", [])
                ]
                memory.sessions = [
                    SessionSummary.from_dict(s)
                    for s in data.get("sessions", [])
                ]
                memory.preferences = data.get("preferences", {})

            except (json.JSONDecodeError, KeyError, TypeError):
                # Corrupted file - start fresh
                pass

        return memory

    def clear(self) -> None:
        """Clear all memory."""
        self.notes.clear()
        self.sessions.clear()
        self.preferences.clear()

    def __len__(self) -> int:
        """Return total number of memory items."""
        return len(self.notes) + len(self.sessions)


def get_memory(project_root: Optional[str | Path] = None) -> ProjectMemory:
    """
    Get project memory, loading from disk if available.

    Args:
        project_root: Project root directory (default: cwd)

    Returns:
        ProjectMemory instance
    """
    root = Path(project_root) if project_root else Path.cwd()
    return ProjectMemory.load(root)


# =============================================================================
# RAG / Semantic Search Support
# =============================================================================


def tokenize(text: str) -> list[str]:
    """
    Simple tokenizer for search.

    Converts text to lowercase and splits on non-alphanumeric characters.
    """
    # Convert to lowercase and split on non-word characters
    tokens = re.findall(r'\b\w+\b', text.lower())
    # Filter out very short tokens and common stop words
    stop_words = {
        'a', 'an', 'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
        'of', 'with', 'by', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
        'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
        'should', 'may', 'might', 'must', 'this', 'that', 'these', 'those',
        'it', 'its', 'i', 'you', 'he', 'she', 'we', 'they', 'what', 'which',
    }
    return [t for t in tokens if len(t) > 1 and t not in stop_words]


def compute_tf(tokens: list[str]) -> dict[str, float]:
    """Compute term frequency for tokens."""
    counts = Counter(tokens)
    total = len(tokens) or 1
    return {term: count / total for term, count in counts.items()}


def compute_idf(documents: list[list[str]]) -> dict[str, float]:
    """Compute inverse document frequency across documents."""
    num_docs = len(documents) or 1
    doc_freq: dict[str, int] = Counter()

    for doc_tokens in documents:
        unique_tokens = set(doc_tokens)
        for token in unique_tokens:
            doc_freq[token] += 1

    return {
        term: math.log(num_docs / (freq + 1)) + 1
        for term, freq in doc_freq.items()
    }


def compute_tfidf(
    tokens: list[str],
    tf: dict[str, float],
    idf: dict[str, float],
) -> dict[str, float]:
    """Compute TF-IDF scores for tokens."""
    return {
        token: tf.get(token, 0) * idf.get(token, 1)
        for token in set(tokens)
    }


def cosine_similarity(vec1: dict[str, float], vec2: dict[str, float]) -> float:
    """Compute cosine similarity between two sparse vectors."""
    # Get common keys
    common_keys = set(vec1.keys()) & set(vec2.keys())
    if not common_keys:
        return 0.0

    # Dot product
    dot = sum(vec1[k] * vec2[k] for k in common_keys)

    # Magnitudes
    mag1 = math.sqrt(sum(v ** 2 for v in vec1.values()))
    mag2 = math.sqrt(sum(v ** 2 for v in vec2.values()))

    if mag1 == 0 or mag2 == 0:
        return 0.0

    return dot / (mag1 * mag2)


@dataclass
class SearchResult:
    """Result from semantic search."""
    note: MemoryNote
    score: float
    matched_terms: list[str]

    def __repr__(self) -> str:
        return f"SearchResult(score={self.score:.3f}, note={self.note.content[:50]}...)"


class MemorySearchIndex:
    """
    In-memory search index for notes.

    Uses TF-IDF for keyword-based semantic search.
    Optionally supports embeddings for true semantic similarity.
    """

    def __init__(self, embedding_func: Optional[Callable[[str], list[float]]] = None):
        """
        Initialize search index.

        Args:
            embedding_func: Optional function to generate embeddings.
                           If not provided, uses TF-IDF keyword search.
        """
        self.embedding_func = embedding_func
        self._notes: list[MemoryNote] = []
        self._tokens: list[list[str]] = []
        self._tfidf_vectors: list[dict[str, float]] = []
        self._embeddings: list[list[float]] = []
        self._idf: dict[str, float] = {}

    def add(self, note: MemoryNote) -> None:
        """Add a note to the index."""
        self._notes.append(note)

        # Tokenize and compute TF
        tokens = tokenize(note.content)
        self._tokens.append(tokens)

        # Recompute IDF with all documents
        self._idf = compute_idf(self._tokens)

        # Recompute TF-IDF for all documents
        self._tfidf_vectors = []
        for doc_tokens in self._tokens:
            tf = compute_tf(doc_tokens)
            tfidf = compute_tfidf(doc_tokens, tf, self._idf)
            self._tfidf_vectors.append(tfidf)

        # Compute embedding if function provided
        if self.embedding_func:
            try:
                embedding = self.embedding_func(note.content)
                self._embeddings.append(embedding)
            except Exception as e:
                logger.warning(f"Failed to compute embedding: {e}")
                self._embeddings.append([])

    def build(self, notes: list[MemoryNote]) -> None:
        """Build index from list of notes."""
        self._notes = []
        self._tokens = []
        self._tfidf_vectors = []
        self._embeddings = []

        for note in notes:
            self._notes.append(note)
            tokens = tokenize(note.content)
            self._tokens.append(tokens)

        # Compute IDF
        self._idf = compute_idf(self._tokens)

        # Compute TF-IDF vectors
        for doc_tokens in self._tokens:
            tf = compute_tf(doc_tokens)
            tfidf = compute_tfidf(doc_tokens, tf, self._idf)
            self._tfidf_vectors.append(tfidf)

        # Compute embeddings if function provided
        if self.embedding_func:
            for note in self._notes:
                try:
                    embedding = self.embedding_func(note.content)
                    self._embeddings.append(embedding)
                except Exception:
                    self._embeddings.append([])

    def search(
        self,
        query: str,
        top_k: int = 5,
        threshold: float = 0.1,
    ) -> list[SearchResult]:
        """
        Search for notes matching query.

        Args:
            query: Search query string
            top_k: Maximum number of results
            threshold: Minimum similarity score

        Returns:
            List of SearchResult sorted by relevance
        """
        if not self._notes:
            return []

        # Tokenize query
        query_tokens = tokenize(query)
        if not query_tokens:
            return []

        # Compute query TF-IDF
        query_tf = compute_tf(query_tokens)
        query_tfidf = compute_tfidf(query_tokens, query_tf, self._idf)

        # Compute similarities
        results = []
        for i, note in enumerate(self._notes):
            doc_tfidf = self._tfidf_vectors[i]
            score = cosine_similarity(query_tfidf, doc_tfidf)

            if score >= threshold:
                # Find matched terms
                matched = [
                    t for t in query_tokens
                    if t in self._tokens[i]
                ]
                results.append(SearchResult(
                    note=note,
                    score=score,
                    matched_terms=matched,
                ))

        # Sort by score descending
        results.sort(key=lambda r: r.score, reverse=True)

        return results[:top_k]

    def semantic_search(
        self,
        query: str,
        top_k: int = 5,
    ) -> list[SearchResult]:
        """
        Search using embeddings if available, else TF-IDF.

        Args:
            query: Search query
            top_k: Maximum results

        Returns:
            List of SearchResult
        """
        if self.embedding_func and self._embeddings:
            # Use embedding-based search
            try:
                query_embedding = self.embedding_func(query)
                results = []

                for i, note in enumerate(self._notes):
                    if i < len(self._embeddings) and self._embeddings[i]:
                        # Cosine similarity between embeddings
                        score = self._embedding_similarity(
                            query_embedding,
                            self._embeddings[i],
                        )
                        results.append(SearchResult(
                            note=note,
                            score=score,
                            matched_terms=[],
                        ))

                results.sort(key=lambda r: r.score, reverse=True)
                return results[:top_k]

            except Exception as e:
                logger.warning(f"Embedding search failed: {e}, falling back to TF-IDF")

        # Fall back to TF-IDF
        return self.search(query, top_k)

    @staticmethod
    def _embedding_similarity(vec1: list[float], vec2: list[float]) -> float:
        """Compute cosine similarity between embedding vectors."""
        if len(vec1) != len(vec2):
            return 0.0

        dot = sum(a * b for a, b in zip(vec1, vec2))
        mag1 = math.sqrt(sum(a ** 2 for a in vec1))
        mag2 = math.sqrt(sum(b ** 2 for b in vec2))

        if mag1 == 0 or mag2 == 0:
            return 0.0

        return dot / (mag1 * mag2)


class RAGMemory:
    """
    RAG-enabled memory with semantic search.

    Wraps ProjectMemory with search capabilities for context retrieval.

    Example:
        rag = RAGMemory.from_project()
        results = rag.retrieve("How do we handle authentication?")
        context = rag.get_relevant_context(query, max_tokens=1000)
    """

    def __init__(
        self,
        memory: ProjectMemory,
        embedding_func: Optional[Callable[[str], list[float]]] = None,
    ):
        self.memory = memory
        self.index = MemorySearchIndex(embedding_func)
        self._build_index()

    def _build_index(self) -> None:
        """Build search index from memory."""
        self.index.build(self.memory.notes)

    def add_note(
        self,
        content: str,
        tags: Optional[list[str]] = None,
        source: str = "user",
    ) -> None:
        """Add note and update index."""
        self.memory.add_note(content, tags, source)
        # Rebuild index (or incrementally add)
        self._build_index()

    def save(self) -> None:
        """Save underlying memory."""
        self.memory.save()

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        threshold: float = 0.1,
    ) -> list[SearchResult]:
        """
        Retrieve relevant notes for a query.

        Args:
            query: Search query
            top_k: Maximum number of results
            threshold: Minimum relevance score

        Returns:
            List of SearchResult
        """
        return self.index.search(query, top_k, threshold)

    def get_relevant_context(
        self,
        query: str,
        max_notes: int = 5,
        max_chars: int = 2000,
    ) -> str:
        """
        Get formatted context string for RAG injection.

        Args:
            query: Query to find relevant context for
            max_notes: Maximum notes to include
            max_chars: Maximum total characters

        Returns:
            Formatted context string
        """
        results = self.retrieve(query, top_k=max_notes)
        if not results:
            return ""

        parts = ["## Relevant Memory"]
        total_chars = 0

        for result in results:
            note_text = f"- {result.note.content}"
            if result.note.tags:
                note_text += f" [tags: {', '.join(result.note.tags)}]"

            if total_chars + len(note_text) > max_chars:
                break

            parts.append(note_text)
            total_chars += len(note_text)

        return "\n".join(parts)

    def get_context_for_task(self, task_description: str) -> str:
        """
        Get memory context relevant to a task.

        Combines general project notes with task-specific retrieval.

        Args:
            task_description: Description of the current task

        Returns:
            Formatted context for system prompt
        """
        # Get task-relevant notes
        relevant = self.get_relevant_context(task_description, max_notes=3, max_chars=1000)

        # Get general project context
        general = self.memory.to_context_prompt()

        if relevant and general:
            return f"{relevant}\n\n{general}"
        return relevant or general

    @classmethod
    def from_project(
        cls,
        project_root: Optional[str | Path] = None,
        embedding_func: Optional[Callable[[str], list[float]]] = None,
    ) -> "RAGMemory":
        """
        Create RAGMemory from project directory.

        Args:
            project_root: Project root directory
            embedding_func: Optional embedding function

        Returns:
            RAGMemory instance
        """
        memory = get_memory(project_root)
        return cls(memory, embedding_func)
