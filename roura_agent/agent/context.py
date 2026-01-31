"""
Roura Agent Context - Tracks read files, conversation history, and constraints.

© Roura.io
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from ..constants import Limits, TokenEstimates


@dataclass
class FileContext:
    """Context for a file that has been read."""
    path: str
    content: str
    read_at: datetime
    lines: int
    size: int

    @classmethod
    def from_path(cls, path: str, content: str) -> FileContext:
        return cls(
            path=str(Path(path).resolve()),
            content=content,
            read_at=datetime.now(),
            lines=content.count("\n") + 1,
            size=len(content.encode("utf-8")),
        )


@dataclass
class FileChange:
    """Record of a file modification for undo support."""
    path: str
    old_content: Optional[str]  # None if file was created
    new_content: str
    action: str  # "created", "modified", "deleted"
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def can_undo(self) -> bool:
        """Check if this change can be undone."""
        return self.action in ("created", "modified")


@dataclass
class Message:
    """A conversation message."""
    role: str  # "user", "assistant", "system", "tool"
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    tool_calls: list[dict] = field(default_factory=list)
    tool_call_id: Optional[str] = None  # For role="tool" messages

    def to_ollama_format(self) -> dict[str, Any]:
        """Convert message to Ollama API format."""
        msg: dict[str, Any] = {
            "role": self.role,
            "content": self.content,
        }

        # Include tool_calls for assistant messages that made calls
        if self.role == "assistant" and self.tool_calls:
            msg["tool_calls"] = self.tool_calls

        # Include tool_call_id for tool result messages
        if self.role == "tool" and self.tool_call_id:
            msg["tool_call_id"] = self.tool_call_id

        return msg

    def estimate_tokens(self) -> int:
        """Estimate token count for this message."""
        # Content tokens
        tokens = len(self.content) // TokenEstimates.CHARS_PER_TOKEN

        # Tool calls add tokens
        if self.tool_calls:
            tokens += len(json.dumps(self.tool_calls)) // TokenEstimates.CHARS_PER_TOKEN

        # Add message overhead
        tokens += TokenEstimates.MESSAGE_OVERHEAD_TOKENS

        return max(tokens, 1)


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

    # Undo history - stack of file changes (most recent first)
    undo_stack: list[FileChange] = field(default_factory=list)
    max_undo_history: int = Limits.MAX_UNDO_HISTORY

    # Tool call counter (resets after user interaction)
    tool_call_count: int = 0
    max_tool_calls: int = Limits.MAX_TOOL_CALLS_BEFORE_CHECK

    # Agentic loop iteration tracking
    iteration: int = 0
    max_iterations: int = Limits.MAX_ITERATIONS
    max_tool_calls_per_turn: int = Limits.MAX_TOOL_CALLS_PER_TURN

    # Token tracking (estimated)
    estimated_tokens: int = 0
    max_context_tokens: int = Limits.MAX_CONTEXT_TOKENS

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

    def add_message(
        self,
        role: str,
        content: str,
        tool_calls: list[dict] = None,
        tool_call_id: Optional[str] = None,
    ) -> None:
        """Add a message to conversation history."""
        msg = Message(
            role=role,
            content=content,
            tool_calls=tool_calls or [],
            tool_call_id=tool_call_id,
        )
        self.messages.append(msg)
        self.estimated_tokens += msg.estimate_tokens()

    def add_tool_result(self, tool_call_id: str, result: Any) -> None:
        """
        Add a tool result message to the conversation.

        This is the result of executing a tool, fed back to the LLM.

        Args:
            tool_call_id: The ID of the tool call this result corresponds to
            result: The tool execution result (will be JSON serialized)
        """
        # Serialize result to string
        if isinstance(result, str):
            content = result
        else:
            try:
                content = json.dumps(result, indent=2, default=str)
            except (TypeError, ValueError):
                content = str(result)

        self.add_message(
            role="tool",
            content=content,
            tool_call_id=tool_call_id,
        )

    def get_messages_for_llm(self) -> list[dict]:
        """Get messages formatted for Ollama API."""
        return [msg.to_ollama_format() for msg in self.messages]

    def start_iteration(self) -> None:
        """Start a new agentic loop iteration."""
        self.iteration += 1

    def can_continue(self) -> tuple[bool, str]:
        """
        Check if the agentic loop can continue.

        Returns:
            (can_continue, reason) tuple
        """
        if self.iteration >= self.max_iterations:
            return False, f"Max iterations reached ({self.max_iterations})"

        if self.tool_call_count >= self.max_tool_calls_per_turn:
            return False, f"Max tool calls per turn ({self.max_tool_calls_per_turn})"

        return True, ""

    def needs_summarization(self) -> bool:
        """Check if context is approaching token limit and needs summarization."""
        return self.estimated_tokens > (self.max_context_tokens * 0.8)

    def reset_iteration(self) -> None:
        """Reset iteration counter (for new user turn)."""
        self.iteration = 0
        self.tool_call_count = 0

    def get_context_summary(self) -> str:
        """Get a summary of current context for display."""
        lines = []

        if self.read_set:
            lines.append(f"\U0001f4c4 {len(self.read_set)} file(s) in context:")
            for path, ctx in list(self.read_set.items())[:5]:
                name = Path(path).name
                lines.append(f"   \u2022 {name} ({ctx.lines} lines)")
            if len(self.read_set) > 5:
                lines.append(f"   \u2022 ... and {len(self.read_set) - 5} more")

        if self.iteration > 0:
            lines.append(f"\U0001f504 Iteration {self.iteration}/{self.max_iterations}")

        if self.tool_call_count > 0:
            lines.append(f"\U0001f527 {self.tool_call_count}/{self.max_tool_calls_per_turn} tool calls this turn")

        if self.estimated_tokens > 0:
            pct = int((self.estimated_tokens / self.max_context_tokens) * 100)
            lines.append(f"\U0001f4ca ~{self.estimated_tokens:,} tokens ({pct}% of context)")

        return "\n".join(lines) if lines else "No context loaded"

    def get_token_status(self) -> str:
        """Get a compact token usage status line for display."""
        if self.estimated_tokens == 0:
            return ""

        pct = int((self.estimated_tokens / self.max_context_tokens) * 100)

        # Color-code based on usage
        if pct >= 80:
            status = "warning"
        elif pct >= 50:
            status = "moderate"
        else:
            status = "normal"

        return f"~{self.estimated_tokens:,} tokens ({pct}%)", status

    def get_token_display(self) -> tuple[str, str]:
        """Get token display with status indicator.

        Returns:
            (display_string, status) where status is 'normal', 'moderate', or 'warning'
        """
        if self.estimated_tokens == 0:
            return "", "normal"

        pct = int((self.estimated_tokens / self.max_context_tokens) * 100)

        # Color-code based on usage
        if pct >= 80:
            status = "warning"
        elif pct >= 50:
            status = "moderate"
        else:
            status = "normal"

        return f"~{self.estimated_tokens:,} tokens ({pct}%)", status

    def record_file_change(
        self,
        path: str,
        old_content: Optional[str],
        new_content: str,
        action: str = "modified",
    ) -> None:
        """
        Record a file change for undo support.

        Args:
            path: Path to the file
            old_content: Content before change (None if file was created)
            new_content: Content after change
            action: Type of change ("created", "modified")
        """
        resolved = str(Path(path).resolve())
        change = FileChange(
            path=resolved,
            old_content=old_content,
            new_content=new_content,
            action=action,
        )
        self.undo_stack.append(change)

        # Trim history if too long
        if len(self.undo_stack) > self.max_undo_history:
            self.undo_stack = self.undo_stack[-self.max_undo_history:]

    def can_undo(self) -> bool:
        """Check if there are changes that can be undone."""
        return len(self.undo_stack) > 0

    def get_last_change(self) -> Optional[FileChange]:
        """Get the most recent change without removing it."""
        return self.undo_stack[-1] if self.undo_stack else None

    def undo_last_change(self) -> Optional[tuple[str, str]]:
        """
        Undo the last file change.

        Returns:
            (path, restored_content) tuple if successful, None if no changes to undo
        """
        if not self.undo_stack:
            return None

        change = self.undo_stack.pop()

        try:
            file_path = Path(change.path)

            if change.action == "created":
                # File was created - delete it
                if file_path.exists():
                    file_path.unlink()
                return change.path, "[file deleted]"

            elif change.action == "modified" and change.old_content is not None:
                # File was modified - restore old content
                file_path.write_text(change.old_content, encoding="utf-8")

                # Update read set with restored content
                self.add_to_read_set(change.path, change.old_content)

                return change.path, change.old_content

        except Exception as e:
            # Put the change back on the stack if undo failed
            self.undo_stack.append(change)
            raise RuntimeError(f"Failed to undo: {e}")

        return None

    def get_undo_history(self, limit: int = 5) -> list[dict]:
        """
        Get recent undo history for display.

        Returns list of dicts with path, action, timestamp.
        """
        history = []
        for change in reversed(self.undo_stack[-limit:]):
            history.append({
                "path": Path(change.path).name,
                "full_path": change.path,
                "action": change.action,
                "timestamp": change.timestamp.strftime("%H:%M:%S"),
            })
        return history

    def clear(self) -> None:
        """Clear all context."""
        self.read_set.clear()
        self.messages.clear()
        self.undo_stack.clear()
        self.tool_call_count = 0
        self.iteration = 0
        self.estimated_tokens = 0
