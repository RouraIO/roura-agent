"""
Roura Agent Session Management - Conversation history persistence.

This module provides:
- Session storage and retrieval
- Session export (JSON/Markdown)
- Session listing and search
- Resume previous sessions

Usage:
    from roura_agent.session import SessionManager, Session

    manager = SessionManager()
    session = manager.create_session()
    session.add_message("user", "Hello")
    manager.save_session(session)

"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .constants import Paths


def get_sessions_dir() -> Path:
    """Get the sessions directory path."""
    # Check for project-local .roura directory first
    local_dir = Path.cwd() / Paths.PROJECT_DIR_NAME / Paths.SESSIONS_DIR
    if local_dir.parent.exists():
        return local_dir

    # Fall back to user config directory
    return Path.home() / Paths.CONFIG_DIR_NAME / Paths.SESSIONS_DIR


@dataclass
class SessionMessage:
    """A message in a session."""
    role: str
    content: str
    timestamp: str
    tool_calls: list[dict] = field(default_factory=list)
    tool_call_id: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "SessionMessage":
        return cls(**data)


@dataclass
class SessionToolCall:
    """Record of a tool call in a session."""
    id: str
    name: str
    arguments: dict
    result: dict
    success: bool
    timestamp: str

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "SessionToolCall":
        return cls(**data)


@dataclass
class Session:
    """A conversation session."""
    id: str
    created_at: str
    updated_at: str
    project_root: Optional[str] = None
    project_name: Optional[str] = None
    model: Optional[str] = None
    title: Optional[str] = None
    messages: list[SessionMessage] = field(default_factory=list)
    tool_calls: list[SessionToolCall] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def add_message(
        self,
        role: str,
        content: str,
        tool_calls: list[dict] = None,
        tool_call_id: Optional[str] = None,
    ) -> None:
        """Add a message to the session."""
        self.messages.append(SessionMessage(
            role=role,
            content=content,
            timestamp=datetime.utcnow().isoformat() + "Z",
            tool_calls=tool_calls or [],
            tool_call_id=tool_call_id,
        ))
        self.updated_at = datetime.utcnow().isoformat() + "Z"

    def add_tool_call(
        self,
        id: str,
        name: str,
        arguments: dict,
        result: dict,
        success: bool,
    ) -> None:
        """Add a tool call record to the session."""
        self.tool_calls.append(SessionToolCall(
            id=id,
            name=name,
            arguments=arguments,
            result=result,
            success=success,
            timestamp=datetime.utcnow().isoformat() + "Z",
        ))
        self.updated_at = datetime.utcnow().isoformat() + "Z"

    def get_summary(self) -> str:
        """Get a brief summary of the session."""
        if self.title:
            return self.title

        # Generate from first user message
        for msg in self.messages:
            if msg.role == "user" and msg.content:
                # Truncate to first 50 chars
                content = msg.content.strip()
                if len(content) > 50:
                    return content[:47] + "..."
                return content

        return f"Session {self.id[:8]}"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "project_root": self.project_root,
            "project_name": self.project_name,
            "model": self.model,
            "title": self.title,
            "messages": [m.to_dict() for m in self.messages],
            "tool_calls": [t.to_dict() for t in self.tool_calls],
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Session":
        return cls(
            id=data["id"],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            project_root=data.get("project_root"),
            project_name=data.get("project_name"),
            model=data.get("model"),
            title=data.get("title"),
            messages=[SessionMessage.from_dict(m) for m in data.get("messages", [])],
            tool_calls=[SessionToolCall.from_dict(t) for t in data.get("tool_calls", [])],
            metadata=data.get("metadata", {}),
        )

    def to_json(self, pretty: bool = True) -> str:
        """Export session to JSON string."""
        indent = 2 if pretty else None
        return json.dumps(self.to_dict(), indent=indent, default=str)

    def to_markdown(self) -> str:
        """Export session to Markdown format."""
        lines = []

        # Header
        lines.append(f"# {self.get_summary()}")
        lines.append("")
        lines.append(f"**Session ID:** `{self.id}`")
        lines.append(f"**Created:** {self.created_at}")
        if self.model:
            lines.append(f"**Model:** {self.model}")
        if self.project_name:
            lines.append(f"**Project:** {self.project_name}")
        lines.append("")
        lines.append("---")
        lines.append("")

        # Messages
        for msg in self.messages:
            if msg.role == "system":
                continue  # Skip system messages in export

            timestamp = msg.timestamp[:19].replace("T", " ")
            role_display = {
                "user": "**User**",
                "assistant": "**Assistant**",
                "tool": "*Tool Result*",
            }.get(msg.role, msg.role)

            lines.append(f"### {role_display} ({timestamp})")
            lines.append("")

            if msg.role == "tool" and msg.tool_call_id:
                lines.append(f"*Tool call ID: {msg.tool_call_id}*")
                lines.append("")

            # Format content
            content = msg.content.strip()
            if msg.role == "tool":
                # Tool results as code block
                lines.append("```json")
                lines.append(content[:2000])  # Truncate long results
                if len(content) > 2000:
                    lines.append("... (truncated)")
                lines.append("```")
            else:
                lines.append(content)

            lines.append("")

            # Show tool calls for assistant messages
            if msg.tool_calls:
                lines.append("**Tool Calls:**")
                for tc in msg.tool_calls:
                    func = tc.get("function", {})
                    lines.append(f"- `{func.get('name', 'unknown')}`")
                lines.append("")

        # Tool call summary
        if self.tool_calls:
            lines.append("---")
            lines.append("")
            lines.append("## Tool Calls Summary")
            lines.append("")
            lines.append("| Tool | Success | Time |")
            lines.append("|------|---------|------|")
            for tc in self.tool_calls[:20]:
                success = "\u2713" if tc.success else "\u2717"
                time = tc.timestamp[11:19]
                lines.append(f"| {tc.name} | {success} | {time} |")
            if len(self.tool_calls) > 20:
                lines.append(f"| ... | | ({len(self.tool_calls) - 20} more) |")

        return "\n".join(lines)


class SessionManager:
    """Manages session storage and retrieval."""

    def __init__(self, sessions_dir: Optional[Path] = None):
        self.sessions_dir = sessions_dir or get_sessions_dir()

    def _ensure_dir(self) -> None:
        """Ensure sessions directory exists."""
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

    def _session_path(self, session_id: str) -> Path:
        """Get path for a session file."""
        return self.sessions_dir / f"{session_id}.json"

    def create_session(
        self,
        project_root: Optional[str] = None,
        project_name: Optional[str] = None,
        model: Optional[str] = None,
    ) -> Session:
        """Create a new session."""
        now = datetime.utcnow().isoformat() + "Z"
        return Session(
            id=str(uuid.uuid4()),
            created_at=now,
            updated_at=now,
            project_root=project_root,
            project_name=project_name,
            model=model,
        )

    def save_session(self, session: Session) -> Path:
        """Save a session to disk."""
        self._ensure_dir()
        path = self._session_path(session.id)
        path.write_text(session.to_json())
        return path

    def load_session(self, session_id: str) -> Optional[Session]:
        """Load a session by ID."""
        path = self._session_path(session_id)
        if not path.exists():
            return None

        try:
            data = json.loads(path.read_text())
            return Session.from_dict(data)
        except Exception:
            return None

    def delete_session(self, session_id: str) -> bool:
        """Delete a session."""
        path = self._session_path(session_id)
        if path.exists():
            path.unlink()
            return True
        return False

    def list_sessions(self, limit: int = 20) -> list[dict]:
        """
        List recent sessions.

        Returns list of dicts with id, created_at, summary.
        """
        self._ensure_dir()

        sessions = []
        for path in sorted(self.sessions_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            if len(sessions) >= limit:
                break

            try:
                data = json.loads(path.read_text())
                session = Session.from_dict(data)
                sessions.append({
                    "id": session.id,
                    "created_at": session.created_at,
                    "updated_at": session.updated_at,
                    "summary": session.get_summary(),
                    "message_count": len(session.messages),
                    "project": session.project_name,
                })
            except Exception:
                continue

        return sessions

    def search_sessions(self, query: str, limit: int = 10) -> list[dict]:
        """Search sessions by content."""
        self._ensure_dir()
        query_lower = query.lower()

        results = []
        for path in self.sessions_dir.glob("*.json"):
            if len(results) >= limit:
                break

            try:
                data = json.loads(path.read_text())
                session = Session.from_dict(data)

                # Search in messages
                for msg in session.messages:
                    if query_lower in msg.content.lower():
                        results.append({
                            "id": session.id,
                            "created_at": session.created_at,
                            "summary": session.get_summary(),
                            "match": msg.content[:100],
                        })
                        break
            except Exception:
                continue

        return results

    def export_session(self, session_id: str, format: str = "json") -> Optional[str]:
        """
        Export a session to string.

        Args:
            session_id: Session ID
            format: "json" or "markdown"
        """
        session = self.load_session(session_id)
        if not session:
            return None

        if format == "markdown":
            return session.to_markdown()
        return session.to_json()

    def get_latest_session(self) -> Optional[Session]:
        """Get the most recent session."""
        self._ensure_dir()

        paths = sorted(
            self.sessions_dir.glob("*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

        if not paths:
            return None

        return self.load_session(paths[0].stem)
