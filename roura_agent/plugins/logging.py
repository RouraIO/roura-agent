"""
Roura Agent Plugin Logging - Structured logging for plugins.

Provides:
- Structured log entries with context
- Log aggregation and filtering
- Plugin-specific log streams
- Log export and persistence

© Roura.io
"""
from __future__ import annotations

import json
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

from ..logging import get_logger

logger = get_logger(__name__)


class LogLevel(str, Enum):
    """Log levels."""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

    @classmethod
    def from_string(cls, level: str) -> "LogLevel":
        """Parse log level from string."""
        return cls(level.lower())

    def numeric(self) -> int:
        """Get numeric value for comparison."""
        return {
            LogLevel.DEBUG: 10,
            LogLevel.INFO: 20,
            LogLevel.WARNING: 30,
            LogLevel.ERROR: 40,
            LogLevel.CRITICAL: 50,
        }[self]


@dataclass
class PluginLogEntry:
    """Structured log entry from a plugin."""
    timestamp: datetime
    level: LogLevel
    plugin_id: str
    plugin_name: str
    message: str
    context: dict[str, Any] = field(default_factory=dict)
    exception: Optional[str] = None
    stack_trace: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "level": self.level.value,
            "plugin_id": self.plugin_id,
            "plugin_name": self.plugin_name,
            "message": self.message,
            "context": self.context,
            "exception": self.exception,
            "stack_trace": self.stack_trace,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: dict) -> "PluginLogEntry":
        return cls(
            timestamp=datetime.fromisoformat(data["timestamp"]),
            level=LogLevel.from_string(data["level"]),
            plugin_id=data["plugin_id"],
            plugin_name=data["plugin_name"],
            message=data["message"],
            context=data.get("context", {}),
            exception=data.get("exception"),
            stack_trace=data.get("stack_trace"),
        )

    def format(self, include_context: bool = False) -> str:
        """Format log entry as string."""
        parts = [
            self.timestamp.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
            f"[{self.level.value.upper():8s}]",
            f"[{self.plugin_name}]",
            self.message,
        ]

        if include_context and self.context:
            parts.append(f"| {json.dumps(self.context)}")

        if self.exception:
            parts.append(f"| Exception: {self.exception}")

        return " ".join(parts)


class PluginLogFilter:
    """Filter for plugin logs."""

    def __init__(
        self,
        min_level: Optional[LogLevel] = None,
        plugin_ids: Optional[list[str]] = None,
        plugin_names: Optional[list[str]] = None,
        contains: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ):
        self.min_level = min_level
        self.plugin_ids = set(plugin_ids) if plugin_ids else None
        self.plugin_names = set(plugin_names) if plugin_names else None
        self.contains = contains.lower() if contains else None
        self.start_time = start_time
        self.end_time = end_time

    def matches(self, entry: PluginLogEntry) -> bool:
        """Check if entry matches filter."""
        if self.min_level and entry.level.numeric() < self.min_level.numeric():
            return False

        if self.plugin_ids and entry.plugin_id not in self.plugin_ids:
            return False

        if self.plugin_names and entry.plugin_name not in self.plugin_names:
            return False

        if self.contains and self.contains not in entry.message.lower():
            return False

        if self.start_time and entry.timestamp < self.start_time:
            return False

        if self.end_time and entry.timestamp > self.end_time:
            return False

        return True


class PluginLogger:
    """
    Logger for a specific plugin.

    Provides structured logging with automatic context injection.
    """

    def __init__(
        self,
        plugin_id: str,
        plugin_name: str,
        aggregator: "PluginLogAggregator",
    ):
        self._plugin_id = plugin_id
        self._plugin_name = plugin_name
        self._aggregator = aggregator
        self._default_context: dict[str, Any] = {}

    def set_context(self, key: str, value: Any) -> None:
        """Set default context value."""
        self._default_context[key] = value

    def clear_context(self, key: Optional[str] = None) -> None:
        """Clear context value(s)."""
        if key:
            self._default_context.pop(key, None)
        else:
            self._default_context.clear()

    def _log(
        self,
        level: LogLevel,
        message: str,
        context: Optional[dict[str, Any]] = None,
        exception: Optional[Exception] = None,
    ) -> PluginLogEntry:
        """Create and emit log entry."""
        import traceback

        merged_context = {**self._default_context}
        if context:
            merged_context.update(context)

        entry = PluginLogEntry(
            timestamp=datetime.now(),
            level=level,
            plugin_id=self._plugin_id,
            plugin_name=self._plugin_name,
            message=message,
            context=merged_context,
            exception=str(exception) if exception else None,
            stack_trace=traceback.format_exc() if exception else None,
        )

        self._aggregator.add_entry(entry)
        return entry

    def debug(
        self,
        message: str,
        context: Optional[dict[str, Any]] = None,
    ) -> PluginLogEntry:
        """Log debug message."""
        return self._log(LogLevel.DEBUG, message, context)

    def info(
        self,
        message: str,
        context: Optional[dict[str, Any]] = None,
    ) -> PluginLogEntry:
        """Log info message."""
        return self._log(LogLevel.INFO, message, context)

    def warning(
        self,
        message: str,
        context: Optional[dict[str, Any]] = None,
    ) -> PluginLogEntry:
        """Log warning message."""
        return self._log(LogLevel.WARNING, message, context)

    def error(
        self,
        message: str,
        context: Optional[dict[str, Any]] = None,
        exception: Optional[Exception] = None,
    ) -> PluginLogEntry:
        """Log error message."""
        return self._log(LogLevel.ERROR, message, context, exception)

    def critical(
        self,
        message: str,
        context: Optional[dict[str, Any]] = None,
        exception: Optional[Exception] = None,
    ) -> PluginLogEntry:
        """Log critical message."""
        return self._log(LogLevel.CRITICAL, message, context, exception)


LogCallback = Callable[[PluginLogEntry], None]


class PluginLogAggregator:
    """
    Aggregates logs from all plugins.

    Provides:
    - Centralized log storage
    - Log filtering and querying
    - Log callbacks for real-time processing
    - Log persistence
    """

    def __init__(
        self,
        max_entries: int = 10000,
        persist_path: Optional[Path] = None,
    ):
        self._entries: deque[PluginLogEntry] = deque(maxlen=max_entries)
        self._callbacks: list[LogCallback] = []
        self._persist_path = persist_path
        self._lock = threading.Lock()

        # Load persisted logs if available
        if persist_path and persist_path.exists():
            self._load_persisted()

    def add_entry(self, entry: PluginLogEntry) -> None:
        """Add a log entry."""
        with self._lock:
            self._entries.append(entry)

        # Notify callbacks
        for callback in self._callbacks:
            try:
                callback(entry)
            except Exception as e:
                logger.warning(f"Log callback error: {e}")

        # Persist if configured
        if self._persist_path:
            self._persist_entry(entry)

    def get_entries(
        self,
        filter: Optional[PluginLogFilter] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[PluginLogEntry]:
        """Get log entries with optional filtering."""
        with self._lock:
            entries = list(self._entries)

        if filter:
            entries = [e for e in entries if filter.matches(e)]

        # Apply offset and limit
        return entries[offset:offset + limit]

    def get_entries_for_plugin(
        self,
        plugin_id: str,
        min_level: Optional[LogLevel] = None,
        limit: int = 100,
    ) -> list[PluginLogEntry]:
        """Get entries for a specific plugin."""
        filter = PluginLogFilter(
            plugin_ids=[plugin_id],
            min_level=min_level,
        )
        return self.get_entries(filter, limit)

    def get_recent_errors(self, limit: int = 50) -> list[PluginLogEntry]:
        """Get recent error and critical entries."""
        filter = PluginLogFilter(min_level=LogLevel.ERROR)
        return self.get_entries(filter, limit)

    def count_entries(
        self,
        filter: Optional[PluginLogFilter] = None,
    ) -> int:
        """Count entries matching filter."""
        with self._lock:
            if not filter:
                return len(self._entries)
            return sum(1 for e in self._entries if filter.matches(e))

    def clear(self) -> None:
        """Clear all entries."""
        with self._lock:
            self._entries.clear()

    def register_callback(self, callback: LogCallback) -> None:
        """Register a callback for new log entries."""
        self._callbacks.append(callback)

    def unregister_callback(self, callback: LogCallback) -> None:
        """Unregister a callback."""
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def create_logger(self, plugin_id: str, plugin_name: str) -> PluginLogger:
        """Create a logger for a plugin."""
        return PluginLogger(plugin_id, plugin_name, self)

    def export(self, path: Path, filter: Optional[PluginLogFilter] = None) -> int:
        """Export logs to file. Returns number of entries exported."""
        entries = self.get_entries(filter, limit=self._entries.maxlen)
        with path.open("w") as f:
            for entry in entries:
                f.write(entry.to_json() + "\n")
        return len(entries)

    def _persist_entry(self, entry: PluginLogEntry) -> None:
        """Persist a single entry to file."""
        try:
            with self._persist_path.open("a") as f:
                f.write(entry.to_json() + "\n")
        except Exception as e:
            logger.warning(f"Failed to persist log entry: {e}")

    def _load_persisted(self) -> None:
        """Load persisted entries from file."""
        try:
            with self._persist_path.open("r") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        entry = PluginLogEntry.from_dict(json.loads(line))
                        self._entries.append(entry)
            logger.debug(f"Loaded {len(self._entries)} persisted log entries")
        except Exception as e:
            logger.warning(f"Failed to load persisted logs: {e}")


# Global log aggregator
_aggregator: Optional[PluginLogAggregator] = None


def get_plugin_log_aggregator() -> PluginLogAggregator:
    """Get the global plugin log aggregator."""
    global _aggregator
    if _aggregator is None:
        persist_path = Path.home() / ".config" / "roura-agent" / "plugin_logs.jsonl"
        persist_path.parent.mkdir(parents=True, exist_ok=True)
        _aggregator = PluginLogAggregator(persist_path=persist_path)
    return _aggregator


def get_plugin_logger(plugin_id: str, plugin_name: str) -> PluginLogger:
    """Get a logger for a plugin."""
    return get_plugin_log_aggregator().create_logger(plugin_id, plugin_name)
