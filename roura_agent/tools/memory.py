"""
Roura Agent Memory Tool - Store and retrieve project notes.

© Roura.io
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .base import Tool, ToolParam, ToolResult, RiskLevel, registry
from ..memory import ProjectMemory


# Cache for project memory instances
_memory_cache: dict[str, ProjectMemory] = {}


def get_memory(project_root: Optional[str] = None) -> ProjectMemory:
    """Get or create a ProjectMemory instance."""
    root = str(Path(project_root).resolve()) if project_root else str(Path.cwd())

    if root not in _memory_cache:
        _memory_cache[root] = ProjectMemory.load(root)

    return _memory_cache[root]


@dataclass
class MemoryStoreTool(Tool):
    """Store a note in project memory."""

    name: str = "memory.store"
    description: str = "Store a note in project memory for future sessions"
    risk_level: RiskLevel = RiskLevel.SAFE
    parameters: list[ToolParam] = field(default_factory=lambda: [
        ToolParam("note", str, "The note to store", required=True),
        ToolParam("tags", str, "Comma-separated tags (e.g., 'testing,important')", required=False, default=None),
    ])

    def execute(
        self,
        note: str,
        tags: Optional[str] = None,
    ) -> ToolResult:
        """Store a note in memory."""
        try:
            memory = get_memory()

            # Parse tags
            tag_list = []
            if tags:
                tag_list = [t.strip() for t in tags.split(",") if t.strip()]

            memory.add_note(
                content=note,
                tags=tag_list,
                source="agent",
            )
            memory.save()

            return ToolResult(
                success=True,
                output={
                    "stored": True,
                    "note": note,
                    "tags": tag_list,
                    "total_notes": len(memory.notes),
                },
            )

        except Exception as e:
            return ToolResult(
                success=False,
                output=None,
                error=str(e),
            )

    def dry_run(self, note: str, tags: Optional[str] = None) -> str:
        return f"Would store note: {note[:50]}..."


@dataclass
class MemoryRecallTool(Tool):
    """Recall notes from project memory."""

    name: str = "memory.recall"
    description: str = "Recall notes from project memory"
    risk_level: RiskLevel = RiskLevel.SAFE
    parameters: list[ToolParam] = field(default_factory=lambda: [
        ToolParam("tag", str, "Filter by tag (optional)", required=False, default=None),
        ToolParam("count", int, "Number of notes to retrieve (default: 10)", required=False, default=10),
    ])

    def execute(
        self,
        tag: Optional[str] = None,
        count: int = 10,
    ) -> ToolResult:
        """Recall notes from memory."""
        try:
            memory = get_memory()

            if tag:
                notes = memory.get_notes_by_tag(tag)
            else:
                notes = memory.notes

            # Get most recent
            recent = notes[-count:] if len(notes) > count else notes

            return ToolResult(
                success=True,
                output={
                    "count": len(recent),
                    "total_available": len(notes),
                    "filter_tag": tag,
                    "notes": [
                        {
                            "content": n.content,
                            "tags": n.tags,
                            "created_at": n.created_at,
                        }
                        for n in recent
                    ],
                },
            )

        except Exception as e:
            return ToolResult(
                success=False,
                output=None,
                error=str(e),
            )

    def dry_run(self, tag: Optional[str] = None, count: int = 10) -> str:
        filter_str = f" with tag '{tag}'" if tag else ""
        return f"Would recall up to {count} notes{filter_str}"


@dataclass
class MemoryClearTool(Tool):
    """Clear project memory."""

    name: str = "memory.clear"
    description: str = "Clear all notes from project memory"
    risk_level: RiskLevel = RiskLevel.MODERATE
    parameters: list[ToolParam] = field(default_factory=lambda: [])

    def execute(self) -> ToolResult:
        """Clear all memory."""
        try:
            memory = get_memory()
            count = len(memory.notes)
            memory.clear()
            memory.save()

            return ToolResult(
                success=True,
                output={
                    "cleared": True,
                    "notes_removed": count,
                },
            )

        except Exception as e:
            return ToolResult(
                success=False,
                output=None,
                error=str(e),
            )

    def dry_run(self) -> str:
        return "Would clear all project memory"


# Create and register tool instances
memory_store = MemoryStoreTool()
memory_recall = MemoryRecallTool()
memory_clear = MemoryClearTool()

registry.register(memory_store)
registry.register(memory_recall)
registry.register(memory_clear)


# Convenience functions
def store_note(note: str, tags: Optional[str] = None) -> ToolResult:
    """Store a note in project memory."""
    return memory_store.execute(note=note, tags=tags)


def recall_notes(tag: Optional[str] = None, count: int = 10) -> ToolResult:
    """Recall notes from project memory."""
    return memory_recall.execute(tag=tag, count=count)


def clear_memory() -> ToolResult:
    """Clear project memory."""
    return memory_clear.execute()
