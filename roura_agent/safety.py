"""
Roura Agent Safety Controls - Blast radius limits and safety guards.

Prevents runaway modifications and protects sensitive directories.

© Roura.io
"""
from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class BlastRadiusLimits:
    """Configurable limits for modification scope."""

    # Maximum files that can be modified in a single session
    max_files_per_session: int = 20

    # Maximum files that can be modified in a single turn
    max_files_per_turn: int = 10

    # Maximum lines of code per single file edit
    max_loc_per_edit: int = 500

    # Maximum total lines of code across all edits in a turn
    max_loc_per_turn: int = 2000

    # Forbidden directories (cannot read or write)
    forbidden_dirs: list[str] = field(default_factory=lambda: [
        ".git",
        "node_modules",
        ".venv",
        "venv",
        "__pycache__",
        ".tox",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "dist",
        "build",
        ".eggs",
        "*.egg-info",
        ".cache",
        ".npm",
        ".yarn",
    ])

    # Forbidden file patterns (cannot modify)
    forbidden_files: list[str] = field(default_factory=lambda: [
        ".env",
        ".env.*",
        "*.pem",
        "*.key",
        "id_rsa",
        "id_ed25519",
        "credentials.json",
        "secrets.json",
        "*.p12",
        "*.pfx",
    ])

    # Allowed file patterns (if set, only these can be modified)
    allowlist: Optional[list[str]] = None

    # Blocked file patterns (if set, these cannot be modified)
    blocklist: Optional[list[str]] = None


@dataclass
class SessionState:
    """Track modifications during a session."""

    files_modified: set[str] = field(default_factory=set)
    files_read: set[str] = field(default_factory=set)
    total_loc_changed: int = 0
    turn_files_modified: set[str] = field(default_factory=set)
    turn_loc_changed: int = 0

    def start_new_turn(self):
        """Reset turn-specific counters."""
        self.turn_files_modified = set()
        self.turn_loc_changed = 0

    def record_modification(self, file_path: str, loc_changed: int):
        """Record a file modification."""
        self.files_modified.add(file_path)
        self.turn_files_modified.add(file_path)
        self.total_loc_changed += loc_changed
        self.turn_loc_changed += loc_changed

    def record_read(self, file_path: str):
        """Record a file read."""
        self.files_read.add(file_path)


# Global defaults
DEFAULT_LIMITS = BlastRadiusLimits()
_session_state: Optional[SessionState] = None


def get_session_state() -> SessionState:
    """Get or create the session state."""
    global _session_state
    if _session_state is None:
        _session_state = SessionState()
    return _session_state


def reset_session_state():
    """Reset the session state."""
    global _session_state
    _session_state = SessionState()


def start_new_turn():
    """Start a new turn, resetting turn-specific limits."""
    get_session_state().start_new_turn()


def is_path_in_pattern(path: str, patterns: list[str]) -> bool:
    """Check if a path matches any of the patterns."""
    path_obj = Path(path)

    for pattern in patterns:
        # Check each part of the path
        for part in path_obj.parts:
            if fnmatch.fnmatch(part, pattern):
                return True

        # Also check the full path
        if fnmatch.fnmatch(str(path_obj), pattern):
            return True
        if fnmatch.fnmatch(path_obj.name, pattern):
            return True

    return False


def check_path_allowed(
    file_path: str,
    limits: Optional[BlastRadiusLimits] = None,
) -> tuple[bool, Optional[str]]:
    """
    Check if a file path is allowed for modification.

    Returns:
        Tuple of (allowed, error_message)
    """
    if limits is None:
        limits = DEFAULT_LIMITS

    path = Path(file_path).resolve()

    # Check forbidden directories
    if is_path_in_pattern(str(path), limits.forbidden_dirs):
        return False, f"Path is in a forbidden directory: {file_path}"

    # Check forbidden files
    if is_path_in_pattern(str(path), limits.forbidden_files):
        return False, f"File matches a forbidden pattern: {file_path}"

    # Check blocklist
    if limits.blocklist and is_path_in_pattern(str(path), limits.blocklist):
        return False, f"File is in the blocklist: {file_path}"

    # Check allowlist (if set, file must match)
    if limits.allowlist:
        if not is_path_in_pattern(str(path), limits.allowlist):
            return False, f"File is not in the allowlist: {file_path}"

    return True, None


def check_modification_allowed(
    file_path: str,
    loc_to_change: int,
    limits: Optional[BlastRadiusLimits] = None,
) -> tuple[bool, Optional[str]]:
    """
    Check if a modification is allowed within blast radius limits.

    Returns:
        Tuple of (allowed, error_message)
    """
    if limits is None:
        limits = DEFAULT_LIMITS

    state = get_session_state()

    # Check if path is allowed
    allowed, error = check_path_allowed(file_path, limits)
    if not allowed:
        return False, error

    # Check LOC per edit
    if loc_to_change > limits.max_loc_per_edit:
        return False, f"Edit exceeds max LOC per edit ({loc_to_change} > {limits.max_loc_per_edit})"

    # Check files per turn (if this is a new file for this turn)
    if file_path not in state.turn_files_modified:
        if len(state.turn_files_modified) >= limits.max_files_per_turn:
            return False, f"Turn limit reached: max {limits.max_files_per_turn} files per turn"

    # Check files per session (if this is a new file for this session)
    if file_path not in state.files_modified:
        if len(state.files_modified) >= limits.max_files_per_session:
            return False, f"Session limit reached: max {limits.max_files_per_session} files per session"

    # Check LOC per turn
    if state.turn_loc_changed + loc_to_change > limits.max_loc_per_turn:
        return False, f"Turn LOC limit exceeded ({state.turn_loc_changed + loc_to_change} > {limits.max_loc_per_turn})"

    return True, None


def record_modification(file_path: str, loc_changed: int):
    """Record a successful modification."""
    get_session_state().record_modification(file_path, loc_changed)


def get_session_stats() -> dict:
    """Get current session statistics."""
    state = get_session_state()
    return {
        "files_modified": len(state.files_modified),
        "files_read": len(state.files_read),
        "total_loc_changed": state.total_loc_changed,
        "turn_files_modified": len(state.turn_files_modified),
        "turn_loc_changed": state.turn_loc_changed,
    }


def format_limits_warning(limits: BlastRadiusLimits) -> str:
    """Format a human-readable warning about the limits."""
    return f"""Blast Radius Limits Active:
- Max files per turn: {limits.max_files_per_turn}
- Max files per session: {limits.max_files_per_session}
- Max LOC per edit: {limits.max_loc_per_edit}
- Max LOC per turn: {limits.max_loc_per_turn}
- Forbidden dirs: {', '.join(limits.forbidden_dirs[:5])}{'...' if len(limits.forbidden_dirs) > 5 else ''}"""


# Runtime mode flags
class SafetyMode:
    """Global safety mode settings."""

    dry_run: bool = False
    readonly: bool = False
    limits: BlastRadiusLimits = DEFAULT_LIMITS

    @classmethod
    def enable_dry_run(cls):
        """Enable dry-run mode (no actual modifications)."""
        cls.dry_run = True

    @classmethod
    def enable_readonly(cls):
        """Enable readonly mode (no writes allowed)."""
        cls.readonly = True

    @classmethod
    def set_limits(cls, limits: BlastRadiusLimits):
        """Set custom blast radius limits."""
        cls.limits = limits

    @classmethod
    def reset(cls):
        """Reset to defaults."""
        cls.dry_run = False
        cls.readonly = False
        cls.limits = DEFAULT_LIMITS


def is_dry_run() -> bool:
    """Check if dry-run mode is active."""
    return SafetyMode.dry_run


def is_readonly() -> bool:
    """Check if readonly mode is active."""
    return SafetyMode.readonly


def check_write_allowed() -> tuple[bool, Optional[str]]:
    """Check if writes are allowed in current mode."""
    if SafetyMode.readonly:
        return False, "Readonly mode is active. No writes allowed."
    if SafetyMode.dry_run:
        return False, "Dry-run mode is active. Would write but skipping."
    return True, None
