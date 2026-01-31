"""
Roura Agent Logging - Structured logging system with JSON output.

This module provides enterprise-grade logging with:
- JSON-formatted logs for machine parsing
- Log rotation and retention
- Contextual information (session, tool, user)
- Multiple output targets (file, console)

Usage:
    from roura_agent.logging import get_logger, setup_logging

    logger = get_logger(__name__)
    logger.info("Operation completed", tool="fs.write", path="/path/to/file")

"""
from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Optional

from .constants import Defaults, Paths
from .secrets import redact_secrets_in_content


# Log directory
def get_log_dir() -> Path:
    """Get the log directory path."""
    # Check for project-local .roura directory first
    local_dir = Path.cwd() / Paths.PROJECT_DIR_NAME / Paths.LOGS_DIR
    if local_dir.parent.exists():
        return local_dir

    # Fall back to user config directory
    return Path.home() / Paths.CONFIG_DIR_NAME / Paths.LOGS_DIR


@dataclass
class LogContext:
    """Contextual information for log entries."""
    session_id: Optional[str] = None
    tool_name: Optional[str] = None
    user_id: Optional[str] = None
    project_root: Optional[str] = None
    extra: dict = field(default_factory=dict)


# Global context
_global_context = LogContext()


def set_log_context(
    session_id: Optional[str] = None,
    tool_name: Optional[str] = None,
    user_id: Optional[str] = None,
    project_root: Optional[str] = None,
    **extra,
) -> None:
    """Set global logging context."""
    global _global_context
    if session_id is not None:
        _global_context.session_id = session_id
    if tool_name is not None:
        _global_context.tool_name = tool_name
    if user_id is not None:
        _global_context.user_id = user_id
    if project_root is not None:
        _global_context.project_root = project_root
    _global_context.extra.update(extra)


def clear_log_context() -> None:
    """Clear global logging context."""
    global _global_context
    _global_context = LogContext()


class SecretRedactingFilter(logging.Filter):
    """Filter that redacts secrets from log messages and extra data."""

    def __init__(self, enabled: bool = True):
        super().__init__()
        self.enabled = enabled

    def filter(self, record: logging.LogRecord) -> bool:
        """Redact secrets from log record. Always returns True (allows log)."""
        if not self.enabled:
            return True

        # Redact the main message
        if record.msg:
            record.msg = redact_secrets_in_content(str(record.msg))

        # Redact extra fields
        for key in list(record.__dict__.keys()):
            if key not in (
                "name", "msg", "args", "created", "filename", "funcName",
                "levelname", "levelno", "lineno", "module", "msecs",
                "pathname", "process", "processName", "relativeCreated",
                "stack_info", "exc_info", "exc_text", "thread", "threadName",
                "message", "asctime",
            ):
                value = getattr(record, key)
                if isinstance(value, str):
                    setattr(record, key, redact_secrets_in_content(value))
                elif isinstance(value, dict):
                    setattr(record, key, self._redact_dict(value))

        return True

    def _redact_dict(self, d: dict) -> dict:
        """Recursively redact secrets in a dictionary."""
        result = {}
        for key, value in d.items():
            if isinstance(value, str):
                result[key] = redact_secrets_in_content(value)
            elif isinstance(value, dict):
                result[key] = self._redact_dict(value)
            elif isinstance(value, list):
                result[key] = [
                    self._redact_dict(v) if isinstance(v, dict)
                    else redact_secrets_in_content(v) if isinstance(v, str)
                    else v
                    for v in value
                ]
            else:
                result[key] = value
        return result


# Global flag for redaction
_redaction_enabled = True


def enable_secret_redaction(enabled: bool = True) -> None:
    """Enable or disable secret redaction in logs."""
    global _redaction_enabled
    _redaction_enabled = enabled


class JSONFormatter(logging.Formatter):
    """JSON log formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add location info
        log_entry["location"] = {
            "file": record.filename,
            "line": record.lineno,
            "function": record.funcName,
        }

        # Add global context
        if _global_context.session_id:
            log_entry["session_id"] = _global_context.session_id
        if _global_context.tool_name:
            log_entry["tool"] = _global_context.tool_name
        if _global_context.user_id:
            log_entry["user_id"] = _global_context.user_id
        if _global_context.project_root:
            log_entry["project"] = _global_context.project_root
        if _global_context.extra:
            log_entry["context"] = _global_context.extra

        # Add extra fields from the log call
        extra_fields = {}
        for key, value in record.__dict__.items():
            if key not in (
                "name", "msg", "args", "created", "filename", "funcName",
                "levelname", "levelno", "lineno", "module", "msecs",
                "pathname", "process", "processName", "relativeCreated",
                "stack_info", "exc_info", "exc_text", "thread", "threadName",
                "message", "asctime",
            ):
                extra_fields[key] = value

        if extra_fields:
            log_entry["data"] = extra_fields

        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, default=str)


class TextFormatter(logging.Formatter):
    """Human-readable text formatter for console output."""

    COLORS = {
        "DEBUG": "\033[36m",    # Cyan
        "INFO": "\033[32m",     # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",    # Red
        "CRITICAL": "\033[35m", # Magenta
    }
    RESET = "\033[0m"

    def __init__(self, use_colors: bool = True):
        super().__init__()
        self.use_colors = use_colors and sys.stderr.isatty()

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as text."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        level = record.levelname

        if self.use_colors:
            color = self.COLORS.get(level, "")
            level_str = f"{color}{level:8}{self.RESET}"
        else:
            level_str = f"{level:8}"

        message = record.getMessage()

        # Format: [HH:MM:SS] LEVEL    logger: message
        output = f"[{timestamp}] {level_str} {record.name}: {message}"

        # Add extra fields
        extra_parts = []
        for key, value in record.__dict__.items():
            if key not in (
                "name", "msg", "args", "created", "filename", "funcName",
                "levelname", "levelno", "lineno", "module", "msecs",
                "pathname", "process", "processName", "relativeCreated",
                "stack_info", "exc_info", "exc_text", "thread", "threadName",
                "message", "asctime",
            ):
                extra_parts.append(f"{key}={value}")

        if extra_parts:
            output += f" ({', '.join(extra_parts)})"

        # Add exception info
        if record.exc_info:
            output += "\n" + self.formatException(record.exc_info)

        return output


class RouraLogger(logging.Logger):
    """Extended logger with structured logging support."""

    def _log_with_extra(
        self,
        level: int,
        msg: str,
        args: tuple = (),
        exc_info: Any = None,
        stack_info: bool = False,
        **kwargs,
    ) -> None:
        """Log with extra keyword arguments as structured data."""
        extra = kwargs
        super()._log(level, msg, args, exc_info=exc_info, stack_info=stack_info, extra=extra)

    def debug(self, msg: str, *args, **kwargs) -> None:
        self._log_with_extra(logging.DEBUG, msg, args, **kwargs)

    def info(self, msg: str, *args, **kwargs) -> None:
        self._log_with_extra(logging.INFO, msg, args, **kwargs)

    def warning(self, msg: str, *args, **kwargs) -> None:
        self._log_with_extra(logging.WARNING, msg, args, **kwargs)

    def error(self, msg: str, *args, **kwargs) -> None:
        self._log_with_extra(logging.ERROR, msg, args, **kwargs)

    def critical(self, msg: str, *args, **kwargs) -> None:
        self._log_with_extra(logging.CRITICAL, msg, args, **kwargs)


# Set custom logger class
logging.setLoggerClass(RouraLogger)


def setup_logging(
    level: str = Defaults.LOG_LEVEL,
    log_format: str = Defaults.LOG_FORMAT,
    log_to_file: bool = True,
    log_to_console: bool = False,
    console_level: str = "WARNING",
    redact_secrets: bool = True,
) -> None:
    """
    Set up the logging system.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_format: Output format ("json" or "text")
        log_to_file: Whether to write logs to file
        log_to_console: Whether to write logs to console
        console_level: Log level for console output
        redact_secrets: Whether to redact secrets from log output
    """
    global _redaction_enabled
    _redaction_enabled = redact_secrets

    root_logger = logging.getLogger("roura_agent")
    root_logger.setLevel(getattr(logging, level.upper()))

    # Clear existing handlers and filters
    root_logger.handlers.clear()
    root_logger.filters.clear()

    # Add secret redacting filter to root logger
    root_logger.addFilter(SecretRedactingFilter(enabled=redact_secrets))

    # File handler
    if log_to_file:
        log_dir = get_log_dir()
        log_dir.mkdir(parents=True, exist_ok=True)

        log_file = log_dir / "roura-agent.log"

        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=Defaults.LOG_MAX_SIZE_MB * 1024 * 1024,
            backupCount=Defaults.LOG_BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setLevel(getattr(logging, level.upper()))

        if log_format == "json":
            file_handler.setFormatter(JSONFormatter())
        else:
            file_handler.setFormatter(TextFormatter(use_colors=False))

        root_logger.addHandler(file_handler)

    # Console handler
    if log_to_console:
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setLevel(getattr(logging, console_level.upper()))
        console_handler.setFormatter(TextFormatter(use_colors=True))
        root_logger.addHandler(console_handler)


def get_logger(name: str) -> RouraLogger:
    """
    Get a logger instance.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Logger instance with structured logging support
    """
    if not name.startswith("roura_agent"):
        name = f"roura_agent.{name}"
    return logging.getLogger(name)  # type: ignore


# Convenience loggers for common categories
def get_agent_logger() -> RouraLogger:
    """Get logger for agent operations."""
    return get_logger("agent")


def get_tool_logger() -> RouraLogger:
    """Get logger for tool operations."""
    return get_logger("tools")


def get_llm_logger() -> RouraLogger:
    """Get logger for LLM operations."""
    return get_logger("llm")


def get_api_logger() -> RouraLogger:
    """Get logger for API operations."""
    return get_logger("api")


# Log event helpers
def log_tool_call(tool_name: str, args: dict, logger: Optional[RouraLogger] = None) -> None:
    """Log a tool call event."""
    logger = logger or get_tool_logger()
    logger.info(
        f"Tool call: {tool_name}",
        tool=tool_name,
        arguments=args,
        event_type="tool_call",
    )


def log_tool_result(tool_name: str, success: bool, error: Optional[str] = None, logger: Optional[RouraLogger] = None) -> None:
    """Log a tool result event."""
    logger = logger or get_tool_logger()
    if success:
        logger.info(
            f"Tool success: {tool_name}",
            tool=tool_name,
            success=True,
            event_type="tool_result",
        )
    else:
        logger.warning(
            f"Tool failed: {tool_name}",
            tool=tool_name,
            success=False,
            error=error,
            event_type="tool_result",
        )


def log_llm_request(model: str, message_count: int, has_tools: bool, logger: Optional[RouraLogger] = None) -> None:
    """Log an LLM request event."""
    logger = logger or get_llm_logger()
    logger.info(
        f"LLM request: {model}",
        model=model,
        message_count=message_count,
        has_tools=has_tools,
        event_type="llm_request",
    )


def log_llm_response(model: str, tokens: int, tool_calls: int, logger: Optional[RouraLogger] = None) -> None:
    """Log an LLM response event."""
    logger = logger or get_llm_logger()
    logger.info(
        f"LLM response: {model}",
        model=model,
        tokens=tokens,
        tool_calls=tool_calls,
        event_type="llm_response",
    )


def log_user_action(action: str, details: Optional[dict] = None, logger: Optional[RouraLogger] = None) -> None:
    """Log a user action event."""
    logger = logger or get_agent_logger()
    logger.info(
        f"User action: {action}",
        action=action,
        details=details or {},
        event_type="user_action",
    )


def log_error(error_code: str, message: str, details: Optional[dict] = None, logger: Optional[RouraLogger] = None) -> None:
    """Log an error event."""
    logger = logger or get_logger("errors")
    logger.error(
        f"[{error_code}] {message}",
        error_code=error_code,
        details=details or {},
        event_type="error",
    )
