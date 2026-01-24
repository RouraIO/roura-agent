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


# --- Write Tool Tests ---

from roura_agent.tools.fs import FsWriteTool, fs_write, write_file


class TestFsWriteTool:
    """Tests for the fs.write tool."""

    def test_tool_properties(self):
        """Tool should have correct properties."""
        assert fs_write.name == "fs.write"
        assert fs_write.risk_level == RiskLevel.MODERATE
        assert fs_write.requires_approval is True

    def test_write_new_file(self, tmp_path):
        """Should create a new file."""
        test_file = tmp_path / "new.txt"
        content = "hello world\n"

        result = write_file(str(test_file), content)

        assert result.success is True
        assert result.output["action"] == "created"
        assert test_file.exists()
        assert test_file.read_text() == content

    def test_overwrite_existing_file(self, tmp_path):
        """Should overwrite an existing file."""
        test_file = tmp_path / "existing.txt"
        test_file.write_text("old content\n")

        result = write_file(str(test_file), "new content\n")

        assert result.success is True
        assert result.output["action"] == "overwritten"
        assert test_file.read_text() == "new content\n"

    def test_write_reports_stats(self, tmp_path):
        """Should report lines and bytes written."""
        test_file = tmp_path / "stats.txt"
        content = "line 1\nline 2\nline 3\n"

        result = write_file(str(test_file), content)

        assert result.success is True
        assert result.output["lines"] == 3
        assert result.output["bytes"] == len(content.encode("utf-8"))

    def test_write_fails_if_parent_missing(self, tmp_path):
        """Should fail if parent directory doesn't exist."""
        test_file = tmp_path / "nonexistent" / "file.txt"

        result = write_file(str(test_file), "content")

        assert result.success is False
        assert "Parent directory" in result.error

    def test_write_creates_parent_dirs(self, tmp_path):
        """Should create parent directories with create_dirs=True."""
        test_file = tmp_path / "deep" / "nested" / "file.txt"

        result = write_file(str(test_file), "content", create_dirs=True)

        assert result.success is True
        assert test_file.exists()
        assert test_file.read_text() == "content"

    def test_write_fails_for_directory(self, tmp_path):
        """Should fail when trying to write to a directory."""
        result = write_file(str(tmp_path), "content")

        assert result.success is False
        assert "directory" in result.error.lower()

    def test_dry_run_description(self, tmp_path):
        """Dry run should describe what would happen."""
        test_file = tmp_path / "test.txt"
        description = fs_write.dry_run(str(test_file), "hello\nworld\n")

        assert "Create" in description
        assert "2 lines" in description

    def test_dry_run_overwrite(self, tmp_path):
        """Dry run should say 'Overwrite' for existing files."""
        test_file = tmp_path / "existing.txt"
        test_file.write_text("old")

        description = fs_write.dry_run(str(test_file), "new")

        assert "Overwrite" in description

    def test_preview_new_file(self, tmp_path):
        """Preview should indicate new file creation."""
        test_file = tmp_path / "new.txt"
        preview = fs_write.preview(str(test_file), "content")

        assert preview["exists"] is False
        assert preview["action"] == "create"
        assert preview["new_content"] == "content"
        assert preview["diff"] is None

    def test_preview_existing_file(self, tmp_path):
        """Preview should show diff for existing file."""
        test_file = tmp_path / "existing.txt"
        test_file.write_text("old\n")

        preview = fs_write.preview(str(test_file), "new\n")

        assert preview["exists"] is True
        assert preview["action"] == "overwrite"
        assert preview["old_content"] == "old\n"
        assert preview["diff"] is not None
        assert "-old" in preview["diff"]
        assert "+new" in preview["diff"]


class TestFsWriteCLI:
    """Tests for the fs write CLI command."""

    def test_write_requires_content(self):
        """Should require --content or --from-file."""
        result = runner.invoke(app, ["fs", "write", "test.txt"])

        assert result.exit_code == 1
        assert "Must provide" in result.output

    def test_write_dry_run(self, tmp_path):
        """Should show preview without writing in dry-run mode."""
        test_file = tmp_path / "test.txt"

        result = runner.invoke(app, [
            "fs", "write", str(test_file),
            "--content", "hello world",
            "--dry-run"
        ])

        assert result.exit_code == 0
        assert "Dry run" in result.output
        assert not test_file.exists()

    def test_write_with_force(self, tmp_path):
        """Should skip approval with --force."""
        test_file = tmp_path / "test.txt"

        result = runner.invoke(app, [
            "fs", "write", str(test_file),
            "--content", "hello world",
            "--force"
        ])

        assert result.exit_code == 0
        assert test_file.exists()
        assert test_file.read_text() == "hello world"

    def test_write_shows_preview_for_new_file(self, tmp_path):
        """Should show content preview for new files."""
        test_file = tmp_path / "test.txt"

        result = runner.invoke(app, [
            "fs", "write", str(test_file),
            "--content", "line 1\nline 2",
            "--dry-run"
        ])

        assert result.exit_code == 0
        assert "CREATE" in result.output
        assert "Content preview" in result.output

    def test_write_shows_diff_for_existing_file(self, tmp_path):
        """Should show diff for existing files."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("old content\n")

        result = runner.invoke(app, [
            "fs", "write", str(test_file),
            "--content", "new content\n",
            "--dry-run"
        ])

        assert result.exit_code == 0
        assert "OVERWRITE" in result.output
        assert "Diff" in result.output

    def test_write_from_file(self, tmp_path):
        """Should read content from another file."""
        source_file = tmp_path / "source.txt"
        source_file.write_text("content from source")
        dest_file = tmp_path / "dest.txt"

        result = runner.invoke(app, [
            "fs", "write", str(dest_file),
            "--from-file", str(source_file),
            "--force"
        ])

        assert result.exit_code == 0
        assert dest_file.read_text() == "content from source"

    def test_write_approval_cancelled(self, tmp_path):
        """Should cancel write when user says no."""
        test_file = tmp_path / "test.txt"

        result = runner.invoke(app, [
            "fs", "write", str(test_file),
            "--content", "hello"
        ], input="no\n")

        assert result.exit_code == 0
        assert "cancelled" in result.output.lower()
        assert not test_file.exists()

    def test_write_approval_accepted(self, tmp_path):
        """Should write when user says yes."""
        test_file = tmp_path / "test.txt"

        result = runner.invoke(app, [
            "fs", "write", str(test_file),
            "--content", "hello"
        ], input="yes\n")

        assert result.exit_code == 0
        assert test_file.exists()
        assert test_file.read_text() == "hello"

    def test_write_json_output(self, tmp_path):
        """Should output JSON with --json flag."""
        test_file = tmp_path / "test.txt"

        result = runner.invoke(app, [
            "fs", "write", str(test_file),
            "--content", "hello",
            "--force",
            "--json"
        ])

        assert result.exit_code == 0
        # Find the JSON object in the output (starts with { and ends with })
        output = result.output
        json_start = output.rfind("{")
        json_end = output.rfind("}") + 1
        json_str = output[json_start:json_end]
        parsed = json.loads(json_str)
        assert "path" in parsed
        assert "action" in parsed


# --- Edit Tool Tests ---

from roura_agent.tools.fs import FsEditTool, fs_edit, edit_file


class TestFsEditTool:
    """Tests for the fs.edit tool."""

    def test_tool_properties(self):
        """Tool should have correct properties."""
        assert fs_edit.name == "fs.edit"
        assert fs_edit.risk_level == RiskLevel.MODERATE
        assert fs_edit.requires_approval is True

    def test_edit_single_occurrence(self, tmp_path):
        """Should replace single occurrence."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello world\n")

        result = edit_file(str(test_file), "hello", "goodbye")

        assert result.success is True
        assert result.output["replacements"] == 1
        assert test_file.read_text() == "goodbye world\n"

    def test_edit_multiple_with_replace_all(self, tmp_path):
        """Should replace all occurrences with replace_all=True."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello hello hello\n")

        result = edit_file(str(test_file), "hello", "hi", replace_all=True)

        assert result.success is True
        assert result.output["replacements"] == 3
        assert test_file.read_text() == "hi hi hi\n"

    def test_edit_fails_on_ambiguous(self, tmp_path):
        """Should fail when multiple occurrences and replace_all=False."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello hello\n")

        result = edit_file(str(test_file), "hello", "hi", replace_all=False)

        assert result.success is False
        assert "2 times" in result.error

    def test_edit_text_not_found(self, tmp_path):
        """Should fail when text not found."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello world\n")

        result = edit_file(str(test_file), "foo", "bar")

        assert result.success is False
        assert "not found" in result.error.lower()

    def test_edit_nonexistent_file(self, tmp_path):
        """Should fail for nonexistent file."""
        result = edit_file(str(tmp_path / "nope.txt"), "old", "new")

        assert result.success is False
        assert "not found" in result.error.lower()

    def test_edit_multiline(self, tmp_path):
        """Should handle multiline replacements."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("line1\nold\nline3\n")

        result = edit_file(str(test_file), "old", "new\nextra")

        assert result.success is True
        assert test_file.read_text() == "line1\nnew\nextra\nline3\n"

    def test_dry_run_description(self, tmp_path):
        """Dry run should describe what would happen."""
        test_file = tmp_path / "test.txt"
        description = fs_edit.dry_run(str(test_file), "old", "new")

        assert "first occurrence" in description
        assert "'old'" in description
        assert "'new'" in description

    def test_dry_run_replace_all(self, tmp_path):
        """Dry run should mention 'all occurrences' with replace_all."""
        test_file = tmp_path / "test.txt"
        description = fs_edit.dry_run(str(test_file), "old", "new", replace_all=True)

        assert "all occurrences" in description

    def test_preview_shows_diff(self, tmp_path):
        """Preview should show unified diff."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello world\n")

        preview = fs_edit.preview(str(test_file), "hello", "goodbye")

        assert preview["occurrences"] == 1
        assert preview["would_replace"] == 1
        assert "-hello world" in preview["diff"]
        assert "+goodbye world" in preview["diff"]

    def test_preview_ambiguous_error(self, tmp_path):
        """Preview should report ambiguous matches."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello hello\n")

        preview = fs_edit.preview(str(test_file), "hello", "hi")

        assert preview["occurrences"] == 2
        assert preview["would_replace"] == 0
        assert "ambiguous" in preview["error"].lower()


class TestFsEditCLI:
    """Tests for the fs edit CLI command."""

    def test_edit_dry_run(self, tmp_path):
        """Should show preview without editing in dry-run mode."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello world\n")

        result = runner.invoke(app, [
            "fs", "edit", str(test_file),
            "--old", "hello",
            "--new", "goodbye",
            "--dry-run"
        ])

        assert result.exit_code == 0
        assert "Dry run" in result.output
        assert test_file.read_text() == "hello world\n"  # Unchanged

    def test_edit_with_force(self, tmp_path):
        """Should skip approval with --force."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello world\n")

        result = runner.invoke(app, [
            "fs", "edit", str(test_file),
            "--old", "hello",
            "--new", "goodbye",
            "--force"
        ])

        assert result.exit_code == 0
        assert test_file.read_text() == "goodbye world\n"

    def test_edit_shows_diff(self, tmp_path):
        """Should show diff in output."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello world\n")

        result = runner.invoke(app, [
            "fs", "edit", str(test_file),
            "--old", "hello",
            "--new", "goodbye",
            "--dry-run"
        ])

        assert result.exit_code == 0
        assert "Diff" in result.output

    def test_edit_approval_cancelled(self, tmp_path):
        """Should cancel edit when user says no."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello world\n")

        result = runner.invoke(app, [
            "fs", "edit", str(test_file),
            "--old", "hello",
            "--new", "goodbye"
        ], input="no\n")

        assert result.exit_code == 0
        assert "cancelled" in result.output.lower()
        assert test_file.read_text() == "hello world\n"  # Unchanged

    def test_edit_approval_accepted(self, tmp_path):
        """Should edit when user says yes."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello world\n")

        result = runner.invoke(app, [
            "fs", "edit", str(test_file),
            "--old", "hello",
            "--new", "goodbye"
        ], input="yes\n")

        assert result.exit_code == 0
        assert test_file.read_text() == "goodbye world\n"

    def test_edit_replace_all_flag(self, tmp_path):
        """Should replace all with --replace-all."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello hello hello\n")

        result = runner.invoke(app, [
            "fs", "edit", str(test_file),
            "--old", "hello",
            "--new", "hi",
            "--replace-all",
            "--force"
        ])

        assert result.exit_code == 0
        assert test_file.read_text() == "hi hi hi\n"

    def test_edit_ambiguous_error(self, tmp_path):
        """Should error on ambiguous match without --replace-all."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello hello\n")

        result = runner.invoke(app, [
            "fs", "edit", str(test_file),
            "--old", "hello",
            "--new", "hi"
        ])

        assert result.exit_code == 1
        assert "ambiguous" in result.output.lower() or "2" in result.output

    def test_edit_text_not_found_error(self, tmp_path):
        """Should error when text not found."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello world\n")

        result = runner.invoke(app, [
            "fs", "edit", str(test_file),
            "--old", "foo",
            "--new", "bar"
        ])

        assert result.exit_code == 1
        assert "not found" in result.output.lower() or "Error" in result.output

    def test_edit_json_output(self, tmp_path):
        """Should output JSON with --json flag."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello world\n")

        result = runner.invoke(app, [
            "fs", "edit", str(test_file),
            "--old", "hello",
            "--new", "goodbye",
            "--force",
            "--json"
        ])

        assert result.exit_code == 0
        output = result.output
        json_start = output.rfind("{")
        json_end = output.rfind("}") + 1
        json_str = output[json_start:json_end]
        parsed = json.loads(json_str)
        assert "path" in parsed
        assert "replacements" in parsed
