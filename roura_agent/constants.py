"""
Roura Agent Constants - Centralized configuration constants.

This module contains all magic numbers and configuration defaults
used throughout the application. Modifying these values allows
fine-tuning behavior without code changes.

Usage:
    from roura_agent.constants import Limits, Timeouts, Defaults

"""
from __future__ import annotations


class Limits:
    """Resource and operation limits."""

    # Agent loop limits
    MAX_ITERATIONS: int = 50
    MAX_TOOL_CALLS_PER_TURN: int = 20
    MAX_TOOL_CALLS_BEFORE_CHECK: int = 10

    # Context limits
    MAX_CONTEXT_TOKENS: int = 32000
    CONTEXT_SUMMARIZE_THRESHOLD: float = 0.75  # Summarize at 75% capacity

    # File operation limits
    MAX_FILE_SIZE_BYTES: int = 10 * 1024 * 1024  # 10 MB
    MAX_FILE_LINES: int = 50000
    MAX_DIFF_LINES: int = 500
    MAX_PREVIEW_LINES: int = 50

    # Undo history
    MAX_UNDO_HISTORY: int = 20

    # Output limits
    MAX_OUTPUT_CHARS: int = 100000
    MAX_SHELL_OUTPUT_CHARS: int = 50000

    # Search limits
    MAX_GLOB_RESULTS: int = 1000
    MAX_GREP_RESULTS: int = 500


class Timeouts:
    """Timeout values in seconds."""

    # LLM timeouts
    LLM_REQUEST: float = 120.0
    LLM_STREAM_CHUNK: float = 30.0

    # Shell command timeouts
    SHELL_DEFAULT: float = 30.0
    SHELL_MAX: float = 300.0

    # Network timeouts
    HTTP_CONNECT: float = 10.0
    HTTP_READ: float = 60.0

    # GitHub/Jira API
    API_REQUEST: float = 30.0


class Retry:
    """Retry configuration."""

    # Retry counts
    MAX_RETRIES_TIMEOUT: int = 3
    MAX_RETRIES_RATE_LIMIT: int = 5
    MAX_RETRIES_CONNECTION: int = 3

    # Backoff configuration
    INITIAL_DELAY: float = 1.0
    MAX_DELAY: float = 30.0
    BACKOFF_MULTIPLIER: float = 2.0

    # Jitter range (0-1)
    JITTER_FACTOR: float = 0.1


class Defaults:
    """Default configuration values."""

    # Ollama defaults
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = ""  # Must be configured

    # GitHub defaults
    GITHUB_DEFAULT_BRANCH: str = "main"

    # Agent defaults
    REQUIRE_PLAN_APPROVAL: bool = True
    REQUIRE_TOOL_APPROVAL: bool = True
    AUTO_READ_ON_MODIFY: bool = True
    STREAM_RESPONSES: bool = True
    SHOW_TOOL_RESULTS: bool = True

    # Logging defaults
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"  # "json" or "text"
    LOG_MAX_SIZE_MB: int = 10
    LOG_BACKUP_COUNT: int = 5


class Paths:
    """Path constants."""

    # Config directory name
    CONFIG_DIR_NAME: str = ".config/roura-agent"

    # Project-local directory
    PROJECT_DIR_NAME: str = ".roura"

    # File names
    CONFIG_FILE: str = "config.json"
    CREDENTIALS_FILE: str = "credentials.json"
    ONBOARDING_MARKER: str = ".onboarded"

    # Subdirectories
    LOGS_DIR: str = "logs"
    SESSIONS_DIR: str = "sessions"
    PLUGINS_DIR: str = "plugins"
    CACHE_DIR: str = "cache"


class TokenEstimates:
    """Token estimation constants."""

    # Characters per token (conservative)
    CHARS_PER_TOKEN: int = 4

    # Overhead for message structure
    MESSAGE_OVERHEAD_TOKENS: int = 4

    # Tool call overhead
    TOOL_CALL_OVERHEAD_TOKENS: int = 50

    # System prompt approximate size
    SYSTEM_PROMPT_TOKENS: int = 500


class RiskThresholds:
    """Thresholds for risk assessment."""

    # Shell command danger patterns
    DANGEROUS_COMMANDS: tuple = (
        "rm -rf",
        "rm -r /",
        "dd if=",
        "mkfs",
        ":(){:|:&};:",
        "> /dev/sda",
        "chmod -R 777 /",
        "wget | sh",
        "curl | sh",
    )

    # Blocked commands (never execute)
    BLOCKED_COMMANDS: tuple = (
        "rm -rf /",
        "rm -rf /*",
        "dd if=/dev/zero of=/dev/sda",
        ":(){:|:&};:",
    )


class UIConstants:
    """UI and display constants."""

    # Progress display
    SPINNER_REFRESH_RATE: int = 10
    LIVE_REFRESH_RATE: int = 15

    # Truncation
    COMMAND_PREVIEW_LENGTH: int = 50
    PATH_PREVIEW_LENGTH: int = 40
    ERROR_PREVIEW_LENGTH: int = 100

    # Tables
    TABLE_MAX_ROWS: int = 50
    TABLE_MAX_COL_WIDTH: int = 60


class APIConstants:
    """API-related constants."""

    # Ollama API
    OLLAMA_CHAT_ENDPOINT: str = "/api/chat"
    OLLAMA_TAGS_ENDPOINT: str = "/api/tags"
    OLLAMA_GENERATE_ENDPOINT: str = "/api/generate"

    # GitHub CLI
    GH_CLI_COMMAND: str = "gh"

    # Jira API
    JIRA_API_VERSION: str = "3"
    JIRA_SEARCH_MAX_RESULTS: int = 50


# Version info
VERSION = "2.0.1"
VERSION_TUPLE = (2, 0, 1)


def get_version() -> str:
    """Get the current version string."""
    return VERSION
