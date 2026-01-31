"""
Roura Agent Shared Execution Context - Singleton context for multi-agent sessions.

This module provides a shared execution context that persists across agent
handoffs, ensuring consistent state tracking for:
- Files read into context (required for write operations)
- File modifications (for undo support)
- Tool execution history
- Session-wide metadata

© Roura.io
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class FileSnapshot:
    """Snapshot of a file at a point in time."""
    path: str
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    agent: Optional[str] = None


@dataclass
class ModificationRecord:
    """Record of a file modification."""
    path: str
    old_content: Optional[str]
    new_content: str
    action: str  # 'created', 'modified', 'deleted'
    agent: str
    timestamp: datetime = field(default_factory=datetime.now)
    tool_name: str = ""


class SharedExecutionContext:
    """
    Singleton execution context shared across all agents in a session.

    This ensures that:
    - File read state is shared (agent B knows agent A read a file)
    - Modifications can be tracked and undone across agent boundaries
    - Tool history is unified for debugging and audit
    - Session state persists between agent handoffs

    Thread-safe for parallel agent execution.
    """

    _instance: Optional[SharedExecutionContext] = None
    _lock = threading.Lock()

    def __new__(cls) -> SharedExecutionContext:
        """Singleton pattern with thread safety."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    instance = super().__new__(cls)
                    instance._initialize()
                    cls._instance = instance
        return cls._instance

    def _initialize(self) -> None:
        """Initialize instance state."""
        self._files_read: Dict[str, FileSnapshot] = {}
        self._modifications: List[ModificationRecord] = []
        self._tool_history: List[Dict[str, Any]] = []
        self._undo_stack: List[ModificationRecord] = []
        self._project_root: Optional[str] = None
        self._session_id: str = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._metadata: Dict[str, Any] = {}
        self._data_lock = threading.RLock()

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton (for testing or new sessions)."""
        with cls._lock:
            cls._instance = None

    @classmethod
    def get_instance(cls) -> SharedExecutionContext:
        """Get the singleton instance."""
        return cls()

    # ===== Properties =====

    @property
    def project_root(self) -> Optional[str]:
        """Get the project root path."""
        return self._project_root

    @project_root.setter
    def project_root(self, value: Optional[str]) -> None:
        """Set the project root path."""
        with self._data_lock:
            self._project_root = value

    @property
    def session_id(self) -> str:
        """Get the current session ID."""
        return self._session_id

    @property
    def files_read(self) -> Dict[str, FileSnapshot]:
        """Get all files read in this session."""
        with self._data_lock:
            return dict(self._files_read)

    @property
    def modifications(self) -> List[ModificationRecord]:
        """Get all modifications made in this session."""
        with self._data_lock:
            return list(self._modifications)

    @property
    def tool_history(self) -> List[Dict[str, Any]]:
        """Get the tool execution history."""
        with self._data_lock:
            return list(self._tool_history)

    # ===== File Read Tracking =====

    def has_read(self, path: str) -> bool:
        """Check if a file has been read in this session."""
        resolved = str(Path(path).resolve())
        with self._data_lock:
            return resolved in self._files_read

    def record_read(
        self,
        path: str,
        content: str,
        agent: Optional[str] = None,
    ) -> None:
        """Record that a file has been read."""
        resolved = str(Path(path).resolve())
        with self._data_lock:
            self._files_read[resolved] = FileSnapshot(
                path=resolved,
                content=content,
                agent=agent,
            )

    def get_file_content(self, path: str) -> Optional[str]:
        """Get the last-read content of a file."""
        resolved = str(Path(path).resolve())
        with self._data_lock:
            snapshot = self._files_read.get(resolved)
            return snapshot.content if snapshot else None

    def clear_read_cache(self, path: Optional[str] = None) -> None:
        """Clear the read cache, optionally for a specific file."""
        with self._data_lock:
            if path:
                resolved = str(Path(path).resolve())
                self._files_read.pop(resolved, None)
            else:
                self._files_read.clear()

    # ===== File Modification Tracking =====

    def record_modification(
        self,
        path: str,
        old_content: Optional[str],
        new_content: str,
        action: str,
        agent: str,
        tool_name: str = "",
    ) -> None:
        """Record a file modification."""
        resolved = str(Path(path).resolve())
        record = ModificationRecord(
            path=resolved,
            old_content=old_content,
            new_content=new_content,
            action=action,
            agent=agent,
            tool_name=tool_name,
        )
        with self._data_lock:
            self._modifications.append(record)
            self._undo_stack.append(record)

            # Update read cache with new content
            self._files_read[resolved] = FileSnapshot(
                path=resolved,
                content=new_content,
                agent=agent,
            )

    def get_modified_files(self) -> List[str]:
        """Get list of files modified in this session."""
        with self._data_lock:
            return list({m.path for m in self._modifications})

    def get_modifications_by_agent(self, agent: str) -> List[ModificationRecord]:
        """Get modifications made by a specific agent."""
        with self._data_lock:
            return [m for m in self._modifications if m.agent == agent]

    # ===== Undo Support =====

    def can_undo(self) -> bool:
        """Check if there are modifications that can be undone."""
        with self._data_lock:
            return len(self._undo_stack) > 0

    def undo_last(self) -> Optional[ModificationRecord]:
        """
        Undo the last modification.

        Returns the modification record that was undone, or None if nothing to undo.
        """
        with self._data_lock:
            if not self._undo_stack:
                return None

            record = self._undo_stack.pop()

            # Restore the old content
            if record.old_content is not None:
                try:
                    file_path = Path(record.path)
                    file_path.write_text(record.old_content, encoding="utf-8")

                    # Update read cache
                    self._files_read[record.path] = FileSnapshot(
                        path=record.path,
                        content=record.old_content,
                        agent="undo",
                    )
                except Exception:
                    # If undo fails, still return the record
                    pass
            elif record.action == "created":
                # If file was created, delete it
                try:
                    Path(record.path).unlink(missing_ok=True)
                    self._files_read.pop(record.path, None)
                except Exception:
                    pass

            return record

    def undo_all_by_agent(self, agent: str) -> List[ModificationRecord]:
        """Undo all modifications by a specific agent (in reverse order)."""
        undone = []
        with self._data_lock:
            # Find all modifications by this agent in the undo stack
            agent_indices = [
                i for i, m in enumerate(self._undo_stack) if m.agent == agent
            ]

            # Undo in reverse order
            for i in reversed(agent_indices):
                record = self._undo_stack.pop(i)
                if record.old_content is not None:
                    try:
                        Path(record.path).write_text(
                            record.old_content, encoding="utf-8"
                        )
                    except Exception:
                        pass
                elif record.action == "created":
                    try:
                        Path(record.path).unlink(missing_ok=True)
                    except Exception:
                        pass
                undone.append(record)

        return undone

    # ===== Tool History =====

    def record_tool_call(
        self,
        tool_name: str,
        args: Dict[str, Any],
        result: Any,
        agent: str,
    ) -> None:
        """Record a tool execution."""
        with self._data_lock:
            self._tool_history.append({
                "tool": tool_name,
                "args": args,
                "success": getattr(result, "success", True),
                "error": getattr(result, "error", None),
                "agent": agent,
                "timestamp": datetime.now().isoformat(),
            })

    def get_tool_history_for_agent(self, agent: str) -> List[Dict[str, Any]]:
        """Get tool history for a specific agent."""
        with self._data_lock:
            return [h for h in self._tool_history if h.get("agent") == agent]

    # ===== Metadata =====

    def set_metadata(self, key: str, value: Any) -> None:
        """Set session metadata."""
        with self._data_lock:
            self._metadata[key] = value

    def get_metadata(self, key: str, default: Any = None) -> Any:
        """Get session metadata."""
        with self._data_lock:
            return self._metadata.get(key, default)

    # ===== Summary =====

    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of the session state."""
        with self._data_lock:
            return {
                "session_id": self._session_id,
                "project_root": self._project_root,
                "files_read_count": len(self._files_read),
                "files_modified_count": len({m.path for m in self._modifications}),
                "tool_calls_count": len(self._tool_history),
                "undo_available": len(self._undo_stack),
                "agents_used": list(
                    {h.get("agent") for h in self._tool_history if h.get("agent")}
                ),
            }


# Convenience function
def get_shared_context() -> SharedExecutionContext:
    """Get the shared execution context singleton."""
    return SharedExecutionContext.get_instance()
