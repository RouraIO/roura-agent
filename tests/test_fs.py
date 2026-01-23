"""
Tests for filesystem tools.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from roura_agent.cli import app
from roura_agent.tools.fs import (
    FsReadTool,
    FsListTool,
    fs_read,
    fs_list,
    read_file,
    list_directory,
)
from roura_agent.tools.base import RiskLevel, ToolResult


runner = CliRunner()


class TestFsReadTool:
    """Tests for the fs.read tool."""

    def test_tool_properties(self):
        """Tool should have correct properties."""
        assert fs_read.name == "fs.read"
        assert fs_read.risk_level == RiskLevel.SAFE
        assert fs_read.requires_approval is False

    def test_read_existing_file(self, tmp_path):
        """Should read contents of existing file."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("line 1\nline 2\nline 3\n")

        result = read_file(str(test_file))

        assert result.success is True
        assert result.output["total_lines"] == 3
        assert "line 1" in result.output["content"]
        assert "line 2" in result.output["content"]
        assert "line 3" in result.output["content"]

    def test_read_nonexistent_file(self, tmp_path):
        """Should fail gracefully for nonexistent file."""
        result = read_file(str(tmp_path / "nonexistent.txt"))

        assert result.success is False
        assert "not found" in result.error.lower()

    def test_read_with_offset(self, tmp_path):
        """Should read from specified offset."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("line 1\nline 2\nline 3\nline 4\nline 5\n")

        result = read_file(str(test_file), offset=3)

        assert result.success is True
        assert "line 1" not in result.output["content"]
        assert "line 2" not in result.output["content"]
        assert "line 3" in result.output["content"]

    def test_read_with_lines_limit(self, tmp_path):
        """Should limit number of lines read."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("line 1\nline 2\nline 3\nline 4\nline 5\n")

        result = read_file(str(test_file), lines=2)

        assert result.success is True
        assert "line 1" in result.output["content"]
        assert "line 2" in result.output["content"]
        assert "line 3" not in result.output["content"]

    def test_read_with_offset_and_lines(self, tmp_path):
        """Should read specific range of lines."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("line 1\nline 2\nline 3\nline 4\nline 5\n")

        result = read_file(str(test_file), offset=2, lines=2)

        assert result.success is True
        assert "line 1" not in result.output["content"]
        assert "line 2" in result.output["content"]
        assert "line 3" in result.output["content"]
        assert "line 4" not in result.output["content"]

    def test_read_directory_fails(self, tmp_path):
        """Should fail when trying to read a directory."""
        result = read_file(str(tmp_path))

        assert result.success is False
        assert "not a file" in result.error.lower()

    def test_line_numbers_in_output(self, tmp_path):
        """Output should include line numbers."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello\nworld\n")

        result = read_file(str(test_file))

        assert result.success is True
        # Line numbers are formatted with tabs
        assert "\t" in result.output["content"]

    def test_dry_run(self, tmp_path):
        """Dry run should describe what would happen."""
        test_file = tmp_path / "test.txt"
        description = fs_read.dry_run(path=str(test_file), lines=10)

        assert "10 lines" in description
        assert str(test_file) in description


class TestFsListTool:
    """Tests for the fs.list tool."""

    def test_tool_properties(self):
        """Tool should have correct properties."""
        assert fs_list.name == "fs.list"
        assert fs_list.risk_level == RiskLevel.SAFE
        assert fs_list.requires_approval is False

    def test_list_directory(self, tmp_path):
        """Should list directory contents."""
        (tmp_path / "file1.txt").write_text("content")
        (tmp_path / "file2.txt").write_text("content")
        (tmp_path / "subdir").mkdir()

        result = list_directory(str(tmp_path))

        assert result.success is True
        assert result.output["count"] == 3

        names = [e["name"] for e in result.output["entries"]]
        assert "file1.txt" in names
        assert "file2.txt" in names
        assert "subdir" in names

    def test_list_hides_dotfiles_by_default(self, tmp_path):
        """Should hide hidden files by default."""
        (tmp_path / "visible.txt").write_text("content")
        (tmp_path / ".hidden").write_text("content")

        result = list_directory(str(tmp_path), show_all=False)

        assert result.success is True
        names = [e["name"] for e in result.output["entries"]]
        assert "visible.txt" in names
        assert ".hidden" not in names

    def test_list_shows_dotfiles_with_all(self, tmp_path):
        """Should show hidden files with --all."""
        (tmp_path / "visible.txt").write_text("content")
        (tmp_path / ".hidden").write_text("content")

        result = list_directory(str(tmp_path), show_all=True)

        assert result.success is True
        names = [e["name"] for e in result.output["entries"]]
        assert "visible.txt" in names
        assert ".hidden" in names

    def test_list_nonexistent_directory(self, tmp_path):
        """Should fail gracefully for nonexistent directory."""
        result = list_directory(str(tmp_path / "nonexistent"))

        assert result.success is False
        assert "not found" in result.error.lower()

    def test_list_file_fails(self, tmp_path):
        """Should fail when trying to list a file."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        result = list_directory(str(test_file))

        assert result.success is False
        assert "not a directory" in result.error.lower()

    def test_entry_types(self, tmp_path):
        """Should correctly identify file and directory types."""
        (tmp_path / "file.txt").write_text("content")
        (tmp_path / "subdir").mkdir()

        result = list_directory(str(tmp_path))

        assert result.success is True
        entries = {e["name"]: e for e in result.output["entries"]}
        assert entries["file.txt"]["type"] == "file"
        assert entries["subdir"]["type"] == "dir"

    def test_file_sizes(self, tmp_path):
        """Should report file sizes correctly."""
        (tmp_path / "small.txt").write_text("hello")
        (tmp_path / "subdir").mkdir()

        result = list_directory(str(tmp_path))

        assert result.success is True
        entries = {e["name"]: e for e in result.output["entries"]}
        assert entries["small.txt"]["size"] == 5
        assert entries["subdir"]["size"] == 0

    def test_dry_run(self, tmp_path):
        """Dry run should describe what would happen."""
        description = fs_list.dry_run(path=str(tmp_path), all=True)

        assert "including hidden" in description
        assert str(tmp_path) in description


class TestFsReadCLI:
    """Tests for the fs read CLI command."""

    def test_read_file_cli(self, tmp_path):
        """Should read file via CLI."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello world\n")

        result = runner.invoke(app, ["fs", "read", str(test_file)])

        assert result.exit_code == 0
        assert "hello world" in result.output

    def test_read_file_cli_json(self, tmp_path):
        """Should output JSON with --json flag."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello\n")

        result = runner.invoke(app, ["fs", "read", str(test_file), "--json"])

        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert "content" in parsed
        assert "total_lines" in parsed

    def test_read_file_cli_with_lines(self, tmp_path):
        """Should respect --lines flag."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("line 1\nline 2\nline 3\n")

        result = runner.invoke(app, ["fs", "read", str(test_file), "--lines", "1"])

        assert result.exit_code == 0
        assert "line 1" in result.output
        assert "line 2" not in result.output

    def test_read_nonexistent_cli(self, tmp_path):
        """Should exit 1 for nonexistent file."""
        result = runner.invoke(app, ["fs", "read", str(tmp_path / "nope.txt")])

        assert result.exit_code == 1
        assert "Error" in result.output


class TestFsListCLI:
    """Tests for the fs list CLI command."""

    def test_list_directory_cli(self, tmp_path):
        """Should list directory via CLI."""
        (tmp_path / "file.txt").write_text("content")

        result = runner.invoke(app, ["fs", "list", str(tmp_path)])

        assert result.exit_code == 0
        assert "file.txt" in result.output

    def test_list_directory_cli_json(self, tmp_path):
        """Should output JSON with --json flag."""
        (tmp_path / "file.txt").write_text("content")

        result = runner.invoke(app, ["fs", "list", str(tmp_path), "--json"])

        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert "entries" in parsed
        assert "count" in parsed

    def test_list_with_all_flag(self, tmp_path):
        """Should show hidden files with --all."""
        (tmp_path / ".hidden").write_text("content")
        (tmp_path / "visible.txt").write_text("content")

        result = runner.invoke(app, ["fs", "list", str(tmp_path), "--all"])

        assert result.exit_code == 0
        assert ".hidden" in result.output
        assert "visible.txt" in result.output

    def test_list_nonexistent_cli(self, tmp_path):
        """Should exit 1 for nonexistent directory."""
        result = runner.invoke(app, ["fs", "list", str(tmp_path / "nope")])

        assert result.exit_code == 1
        assert "Error" in result.output
