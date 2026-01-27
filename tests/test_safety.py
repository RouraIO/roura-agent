"""
Tests for safety controls and blast radius limits.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from roura_agent.safety import (
    BlastRadiusLimits,
    SessionState,
    SafetyMode,
    get_session_state,
    reset_session_state,
    start_new_turn,
    check_path_allowed,
    check_modification_allowed,
    record_modification,
    get_session_stats,
    format_limits_warning,
    is_path_in_pattern,
    is_dry_run,
    is_readonly,
    check_write_allowed,
)


class TestBlastRadiusLimits:
    """Tests for BlastRadiusLimits configuration."""

    def test_default_limits(self):
        """Default limits should be sensible."""
        limits = BlastRadiusLimits()

        assert limits.max_files_per_session == 20
        assert limits.max_files_per_turn == 10
        assert limits.max_loc_per_edit == 500
        assert limits.max_loc_per_turn == 2000
        assert ".git" in limits.forbidden_dirs
        assert "node_modules" in limits.forbidden_dirs
        assert ".env" in limits.forbidden_files
        assert "*.pem" in limits.forbidden_files

    def test_custom_limits(self):
        """Should accept custom limits."""
        limits = BlastRadiusLimits(
            max_files_per_session=5,
            max_files_per_turn=2,
            max_loc_per_edit=100,
        )

        assert limits.max_files_per_session == 5
        assert limits.max_files_per_turn == 2
        assert limits.max_loc_per_edit == 100


class TestSessionState:
    """Tests for SessionState tracking."""

    def test_initial_state(self):
        """Fresh session should have empty state."""
        state = SessionState()

        assert len(state.files_modified) == 0
        assert len(state.files_read) == 0
        assert state.total_loc_changed == 0
        assert len(state.turn_files_modified) == 0
        assert state.turn_loc_changed == 0

    def test_record_modification(self):
        """Should track file modifications."""
        state = SessionState()

        state.record_modification("/path/to/file.py", 50)

        assert "/path/to/file.py" in state.files_modified
        assert "/path/to/file.py" in state.turn_files_modified
        assert state.total_loc_changed == 50
        assert state.turn_loc_changed == 50

    def test_record_multiple_modifications(self):
        """Should accumulate modifications."""
        state = SessionState()

        state.record_modification("/path/a.py", 30)
        state.record_modification("/path/b.py", 20)
        state.record_modification("/path/a.py", 10)  # Same file again

        assert len(state.files_modified) == 2  # Unique files
        assert state.total_loc_changed == 60
        assert state.turn_loc_changed == 60

    def test_start_new_turn(self):
        """New turn should reset turn counters but keep session."""
        state = SessionState()

        state.record_modification("/path/a.py", 50)
        state.start_new_turn()

        assert len(state.files_modified) == 1  # Session keeps track
        assert state.total_loc_changed == 50
        assert len(state.turn_files_modified) == 0  # Turn reset
        assert state.turn_loc_changed == 0

    def test_record_read(self):
        """Should track file reads."""
        state = SessionState()

        state.record_read("/path/file.py")

        assert "/path/file.py" in state.files_read


class TestPathPatternMatching:
    """Tests for path pattern matching."""

    def test_matches_exact_dirname(self):
        """Should match exact directory names."""
        assert is_path_in_pattern("/project/.git/config", [".git"])
        assert is_path_in_pattern("/project/node_modules/pkg", ["node_modules"])

    def test_matches_glob_pattern(self):
        """Should match glob patterns."""
        assert is_path_in_pattern("/project/my.egg-info/file", ["*.egg-info"])
        assert is_path_in_pattern("/home/user/.env.local", [".env.*"])

    def test_matches_filename(self):
        """Should match filenames."""
        assert is_path_in_pattern("/project/.env", [".env"])
        assert is_path_in_pattern("/path/to/key.pem", ["*.pem"])

    def test_no_match(self):
        """Should not match unrelated paths."""
        assert not is_path_in_pattern("/project/src/main.py", [".git", "node_modules"])
        assert not is_path_in_pattern("/project/config.json", [".env", "*.pem"])


class TestCheckPathAllowed:
    """Tests for path allowance checking."""

    def test_allows_normal_path(self):
        """Normal source files should be allowed."""
        allowed, error = check_path_allowed("/project/src/main.py")

        assert allowed is True
        assert error is None

    def test_blocks_git_directory(self):
        """Should block .git directory."""
        allowed, error = check_path_allowed("/project/.git/config")

        assert allowed is False
        assert "forbidden" in error.lower()

    def test_blocks_node_modules(self):
        """Should block node_modules."""
        allowed, error = check_path_allowed("/project/node_modules/pkg/index.js")

        assert allowed is False
        assert "forbidden" in error.lower()

    def test_blocks_env_files(self):
        """Should block .env files."""
        allowed, error = check_path_allowed("/project/.env")

        assert allowed is False
        assert "forbidden" in error.lower()

    def test_blocks_pem_files(self):
        """Should block .pem files."""
        allowed, error = check_path_allowed("/project/private.pem")

        assert allowed is False
        assert "forbidden" in error.lower()

    def test_custom_blocklist(self):
        """Should respect custom blocklist."""
        limits = BlastRadiusLimits(blocklist=["*.secret"])

        allowed, error = check_path_allowed("/project/data.secret", limits)

        assert allowed is False
        assert "blocklist" in error.lower()

    def test_custom_allowlist(self):
        """Should only allow files matching allowlist when set."""
        limits = BlastRadiusLimits(allowlist=["*.py", "*.txt"])

        allowed_py, _ = check_path_allowed("/project/main.py", limits)
        allowed_js, error = check_path_allowed("/project/main.js", limits)

        assert allowed_py is True
        assert allowed_js is False
        assert "allowlist" in error.lower()


class TestCheckModificationAllowed:
    """Tests for modification limit checking."""

    def test_allows_small_edit(self):
        """Small edits should be allowed."""
        allowed, error = check_modification_allowed("/project/main.py", 10)

        assert allowed is True
        assert error is None

    def test_blocks_large_edit(self):
        """Should block edits exceeding LOC limit."""
        limits = BlastRadiusLimits(max_loc_per_edit=100)

        allowed, error = check_modification_allowed("/project/main.py", 150, limits)

        assert allowed is False
        assert "LOC per edit" in error

    def test_blocks_after_turn_limit(self):
        """Should block after turn file limit reached."""
        limits = BlastRadiusLimits(max_files_per_turn=2)

        # First two files OK
        record_modification("/a.py", 10)
        record_modification("/b.py", 10)

        # Third should be blocked
        allowed, error = check_modification_allowed("/c.py", 10, limits)

        assert allowed is False
        assert "Turn limit" in error

    def test_allows_same_file_again(self):
        """Editing the same file again should be allowed."""
        limits = BlastRadiusLimits(max_files_per_turn=2)

        record_modification("/a.py", 10)
        record_modification("/b.py", 10)

        # Same file should be OK
        allowed, error = check_modification_allowed("/a.py", 10, limits)

        assert allowed is True

    def test_blocks_loc_per_turn(self):
        """Should block when turn LOC limit exceeded."""
        limits = BlastRadiusLimits(max_loc_per_turn=100)

        record_modification("/a.py", 80)

        # This would exceed the limit
        allowed, error = check_modification_allowed("/b.py", 30, limits)

        assert allowed is False
        assert "LOC limit" in error


class TestSafetyMode:
    """Tests for SafetyMode settings."""

    def test_default_mode(self):
        """Default should allow all operations."""
        assert not is_dry_run()
        assert not is_readonly()

    def test_dry_run_mode(self):
        """Dry run mode should be settable."""
        SafetyMode.enable_dry_run()

        assert is_dry_run()

        SafetyMode.reset()
        assert not is_dry_run()

    def test_readonly_mode(self):
        """Readonly mode should be settable."""
        SafetyMode.enable_readonly()

        assert is_readonly()

        SafetyMode.reset()
        assert not is_readonly()

    def test_check_write_allowed_in_readonly(self):
        """Writes should be blocked in readonly mode."""
        SafetyMode.enable_readonly()

        allowed, error = check_write_allowed()

        assert allowed is False
        assert "Readonly" in error

    def test_check_write_allowed_in_dry_run(self):
        """Writes should be blocked in dry-run mode."""
        SafetyMode.enable_dry_run()

        allowed, error = check_write_allowed()

        assert allowed is False
        assert "Dry-run" in error


class TestSessionFunctions:
    """Tests for session management functions."""

    def test_get_session_stats(self):
        """Should return session statistics."""
        record_modification("/a.py", 50)
        record_modification("/b.py", 30)

        stats = get_session_stats()

        assert stats["files_modified"] == 2
        assert stats["total_loc_changed"] == 80
        assert stats["turn_files_modified"] == 2
        assert stats["turn_loc_changed"] == 80

    def test_start_new_turn_resets_turn_stats(self):
        """New turn should reset turn stats."""
        record_modification("/a.py", 50)
        start_new_turn()

        stats = get_session_stats()

        assert stats["files_modified"] == 1  # Session total
        assert stats["turn_files_modified"] == 0  # Turn reset
        assert stats["turn_loc_changed"] == 0

    def test_format_limits_warning(self):
        """Should format readable warning."""
        limits = BlastRadiusLimits()

        warning = format_limits_warning(limits)

        assert "Blast Radius Limits" in warning
        assert "10" in warning  # max_files_per_turn
        assert "20" in warning  # max_files_per_session
