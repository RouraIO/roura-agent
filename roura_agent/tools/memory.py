"""
Roura Agent Memory Tool - Store, retrieve, and search project notes.

Provides:
- Note storage with tags
- Note retrieval
- Semantic search (RAG-ready)
- Memory management

© Roura.io
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .base import Tool, ToolParam, ToolResult, RiskLevel, registry
from ..memory import ProjectMemory, RAGMemory


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


@dataclass
class MemorySearchTool(Tool):
    """Search project memory using semantic matching."""

    name: str = "memory.search"
    description: str = "Search project memory for notes matching a query"
    risk_level: RiskLevel = RiskLevel.SAFE
    parameters: list[ToolParam] = field(default_factory=lambda: [
        ToolParam("query", str, "Search query to find relevant notes", required=True),
        ToolParam("count", int, "Maximum number of results (default: 5)", required=False, default=5),
    ])

    def execute(
        self,
        query: str,
        count: int = 5,
    ) -> ToolResult:
        """Search memory for relevant notes."""
        try:
            memory = get_memory()
            rag = RAGMemory(memory)

            results = rag.retrieve(query, top_k=count)

            return ToolResult(
                success=True,
                output={
                    "query": query,
                    "count": len(results),
                    "results": [
                        {
                            "content": r.note.content,
                            "tags": r.note.tags,
                            "score": round(r.score, 3),
                            "matched_terms": r.matched_terms,
                            "created_at": r.note.created_at,
                        }
                        for r in results
                    ],
                },
            )

        except Exception as e:
            return ToolResult(
                success=False,
                output=None,
                error=str(e),
            )

    def dry_run(self, query: str, count: int = 5) -> str:
        return f"Would search memory for: {query}"


@dataclass
class MemoryContextTool(Tool):
    """Get relevant memory context for a task."""

    name: str = "memory.context"
    description: str = "Get memory context relevant to a task for RAG injection"
    risk_level: RiskLevel = RiskLevel.SAFE
    parameters: list[ToolParam] = field(default_factory=lambda: [
        ToolParam("task", str, "Task description to find context for", required=True),
        ToolParam("max_chars", int, "Maximum characters for context (default: 2000)", required=False, default=2000),
    ])

    def execute(
        self,
        task: str,
        max_chars: int = 2000,
    ) -> ToolResult:
        """Get relevant context for a task."""
        try:
            memory = get_memory()
            rag = RAGMemory(memory)

            context = rag.get_context_for_task(task)

            return ToolResult(
                success=True,
                output={
                    "task": task,
                    "context": context,
                    "context_length": len(context),
                },
            )

        except Exception as e:
            return ToolResult(
                success=False,
                output=None,
                error=str(e),
            )

    def dry_run(self, task: str, max_chars: int = 2000) -> str:
        return f"Would get context for task: {task}"


# Create and register tool instances
memory_store = MemoryStoreTool()
memory_recall = MemoryRecallTool()
memory_clear = MemoryClearTool()
memory_search = MemorySearchTool()
memory_context = MemoryContextTool()

registry.register(memory_store)
registry.register(memory_recall)
registry.register(memory_clear)
registry.register(memory_search)
registry.register(memory_context)


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


def search_memory(query: str, count: int = 5) -> ToolResult:
    """Search memory for notes matching query."""
    return memory_search.execute(query=query, count=count)


def get_memory_context(task: str, max_chars: int = 2000) -> ToolResult:
    """Get memory context relevant to a task."""
    return memory_context.execute(task=task, max_chars=max_chars)
