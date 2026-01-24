"""
Roura Agent Context - Tracks read files, conversation history, and constraints.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from datetime import datetime


@dataclass
class FileContext:
    """Context for a file that has been read."""
    path: str
    content: str
    read_at: datetime
    lines: int
    size: int

    @classmethod
    def from_path(cls, path: str, content: str) -> "FileContext":
        return cls(
            path=str(Path(path).resolve()),
            content=content,
            read_at=datetime.now(),
            lines=content.count("\n") + 1,
            size=len(content.encode("utf-8")),
        )


@dataclass
class Message:
    """A conversation message."""
    role: str  # "user", "assistant", "system"
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    tool_calls: list[dict] = field(default_factory=list)


@dataclass
class AgentContext:
    """
    Tracks agent state and enforces constraints.

    Constraints enforced:
    - #6: Never hallucinate file contents (tracked via read_set)
    - #7: Never modify files not read (blocked via can_modify)
    - #5: Max 3 tool calls without re-checking (tracked via tool_call_count)
    """

    # Read set - files the agent has read
    read_set: dict[str, FileContext] = field(default_factory=dict)

    # Conversation history
    messages: list[Message] = field(default_factory=list)

    # Tool call counter (resets after user interaction)
    tool_call_count: int = 0
    max_tool_calls: int = 3

    # Current working directory
    cwd: str = field(default_factory=lambda: str(Path.cwd()))

    # Project root (git root or cwd)
    project_root: Optional[str] = None

    def add_to_read_set(self, path: str, content: str) -> None:
        """Add a file to the read set."""
        resolved = str(Path(path).resolve())
        self.read_set[resolved] = FileContext.from_path(resolved, content)

    def has_read(self, path: str) -> bool:
        """Check if a file has been read."""
        resolved = str(Path(path).resolve())
        return resolved in self.read_set

    def can_modify(self, path: str) -> tuple[bool, str]:
        """
        Check if agent can modify a file.

        Returns (allowed, reason).
        Constraint #7: Never modify files not read.
        """
        resolved = str(Path(path).resolve())

        # New files can always be created
        if not Path(resolved).exists():
            return True, "New file"

        # Existing files must be read first
        if resolved not in self.read_set:
            return False, f"File not read: {path}. Read it first before modifying."

        return True, "File in read set"

    def get_file_content(self, path: str) -> Optional[str]:
        """Get cached content of a read file."""
        resolved = str(Path(path).resolve())
        ctx = self.read_set.get(resolved)
        return ctx.content if ctx else None

    def increment_tool_calls(self) -> bool:
        """
        Increment tool call count.

        Returns True if under limit, False if limit reached.
        Constraint #5: Max 3 tool calls without re-checking.
        """
        self.tool_call_count += 1
        return self.tool_call_count <= self.max_tool_calls

    def reset_tool_calls(self) -> None:
        """Reset tool call counter (after user interaction)."""
        self.tool_call_count = 0

    def needs_user_check(self) -> bool:
        """Check if we need to pause for user confirmation."""
        return self.tool_call_count >= self.max_tool_calls

    def add_message(self, role: str, content: str, tool_calls: list[dict] = None) -> None:
        """Add a message to conversation history."""
        self.messages.append(Message(
            role=role,
            content=content,
            tool_calls=tool_calls or [],
        ))

    def get_messages_for_llm(self) -> list[dict]:
        """Get messages formatted for LLM API."""
        return [
            {"role": msg.role, "content": msg.content}
            for msg in self.messages
        ]

    def get_context_summary(self) -> str:
        """Get a summary of current context for display."""
        lines = []

        if self.read_set:
            lines.append(f"📄 {len(self.read_set)} file(s) in context:")
            for path, ctx in list(self.read_set.items())[:5]:
                name = Path(path).name
                lines.append(f"   • {name} ({ctx.lines} lines)")
            if len(self.read_set) > 5:
                lines.append(f"   • ... and {len(self.read_set) - 5} more")

        if self.tool_call_count > 0:
            lines.append(f"🔧 {self.tool_call_count}/{self.max_tool_calls} tool calls this turn")

        return "\n".join(lines) if lines else "No context loaded"

    def clear(self) -> None:
        """Clear all context."""
        self.read_set.clear()
        self.messages.clear()
        self.tool_call_count = 0
