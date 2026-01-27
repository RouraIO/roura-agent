"""
Roura Agent Persistent Memory - Project memory stored in .roura directory.

© Roura.io
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


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
