"""
Tests for the CLI module.

© Roura.io
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from typer.testing import CliRunner
import json

from roura_agent.cli import app, console


runner = CliRunner()


class TestCLIBasics:
    """Tests for basic CLI functionality."""

    def test_version_flag(self):
        """Test --version flag shows version."""
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "Roura Agent" in result.stdout
        assert "version" in result.stdout

    def test_help_flag(self):
        """Test --help flag shows help."""
        import re
        # Strip ANSI escape codes for reliable text checking
        def strip_ansi(text):
            return re.sub(r'\x1b\[[0-9;]*m', '', text)

        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        stdout = strip_ansi(result.stdout)
        assert "Roura Agent" in stdout
        # Check for provider option - may be displayed as "-p" or "--provider"
        assert "-p" in stdout or "--provider" in stdout or "provider" in stdout.lower()
        assert "--safe-mode" in stdout or "safe-mode" in stdout.lower()

    def test_doctor_command(self):
        """Test doctor command runs."""
        result = runner.invoke(app, ["doctor"])
        # May fail if not all dependencies installed, but should run
        assert result.exit_code in (0, 1)

    def test_tools_command(self):
        """Test tools command lists tools."""
        result = runner.invoke(app, ["tools"])
        assert result.exit_code == 0
        # Should show at least some tools
        assert "fs.read" in result.stdout or "Tool" in result.stdout


class TestFSCommands:
    """Tests for filesystem subcommands."""

    def test_fs_read_nonexistent(self):
        """Test reading nonexistent file."""
        result = runner.invoke(app, ["fs", "read", "/nonexistent/file.txt"])
        assert result.exit_code == 1
        assert "Error" in result.stdout

    def test_fs_list_current_dir(self):
        """Test listing current directory."""
        result = runner.invoke(app, ["fs", "list", "."])
        assert result.exit_code == 0

    def test_fs_write_requires_content(self):
        """Test write requires content."""
        result = runner.invoke(app, ["fs", "write", "/tmp/test.txt"])
        assert result.exit_code == 1
        assert "content" in result.stdout.lower() or "Error" in result.stdout


class TestGitCommands:
    """Tests for git subcommands."""

    def test_git_status_non_repo(self):
        """Test git status in non-repo directory."""
        result = runner.invoke(app, ["git", "status", "/tmp"])
        # May succeed or fail depending on /tmp being a repo
        assert result.exit_code in (0, 1)

    def test_git_log_non_repo(self):
        """Test git log in non-repo directory."""
        result = runner.invoke(app, ["git", "log", "/tmp"])
        assert result.exit_code in (0, 1)


class TestMCPCommands:
    """Tests for MCP subcommands."""

    @patch("roura_agent.tools.mcp.get_mcp_manager")
    def test_mcp_servers_empty(self, mock_get_manager):
        """Test mcp servers with no servers."""
        mock_manager = Mock()
        mock_manager.get_status.return_value = {
            "servers": {},
            "total_tools": 0,
        }
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(app, ["mcp", "servers"])
        assert result.exit_code == 0
        assert "No MCP servers" in result.stdout

    @patch("roura_agent.tools.mcp.get_mcp_manager")
    def test_mcp_servers_json(self, mock_get_manager):
        """Test mcp servers with JSON output."""
        mock_manager = Mock()
        mock_manager.get_status.return_value = {
            "servers": {"test": {"status": "connected", "tools": 2, "resources": 1}},
            "total_tools": 2,
        }
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(app, ["mcp", "servers", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert "servers" in data
        assert data["total_tools"] == 2

    @patch("roura_agent.tools.mcp.get_mcp_manager")
    def test_mcp_tools_empty(self, mock_get_manager):
        """Test mcp tools with no tools."""
        mock_manager = Mock()
        mock_manager.get_all_tools.return_value = []
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(app, ["mcp", "tools"])
        assert result.exit_code == 0
        assert "No MCP tools" in result.stdout

    @patch("roura_agent.tools.mcp.get_mcp_manager")
    def test_mcp_connect_not_found(self, mock_get_manager):
        """Test mcp connect with nonexistent server."""
        mock_manager = Mock()
        mock_manager.get_server.return_value = None
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(app, ["mcp", "connect", "nonexistent"])
        assert result.exit_code == 1
        assert "not found" in result.stdout

    @patch("roura_agent.tools.mcp.get_mcp_manager")
    def test_mcp_disconnect_not_found(self, mock_get_manager):
        """Test mcp disconnect with nonexistent server."""
        mock_manager = Mock()
        mock_manager.get_server.return_value = None
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(app, ["mcp", "disconnect", "nonexistent"])
        assert result.exit_code == 1
        assert "not found" in result.stdout


class TestImageCommands:
    """Tests for image subcommands."""

    @patch("roura_agent.tools.image.read_image")
    def test_image_read_success(self, mock_read):
        """Test image read command."""
        mock_read.return_value = Mock(
            success=True,
            output={
                "path": "/test/image.png",
                "format": "PNG",
                "width": 100,
                "height": 100,
                "file_size": 1024,
            }
        )

        result = runner.invoke(app, ["image", "read", "/test/image.png"])
        assert result.exit_code == 0
        assert "100x100" in result.stdout

    @patch("roura_agent.tools.image.read_image")
    def test_image_read_error(self, mock_read):
        """Test image read error handling."""
        mock_read.return_value = Mock(
            success=False,
            error="File not found"
        )

        result = runner.invoke(app, ["image", "read", "/nonexistent.png"])
        assert result.exit_code == 1
        assert "Error" in result.stdout

    @patch("roura_agent.tools.image.analyze_image")
    def test_image_analyze_success(self, mock_analyze):
        """Test image analyze command."""
        mock_analyze.return_value = Mock(
            success=True,
            output={"analysis": "This is a test image"}
        )

        result = runner.invoke(app, ["image", "analyze", "/test/image.png"])
        assert result.exit_code == 0
        assert "test image" in result.stdout


class TestNotebookCommands:
    """Tests for notebook subcommands."""

    @patch("roura_agent.tools.notebook.read_notebook")
    def test_notebook_read_success(self, mock_read):
        """Test notebook read command."""
        mock_read.return_value = Mock(
            success=True,
            output={
                "path": "/test/notebook.ipynb",
                "cell_count": 3,
                "code_cells": 2,
                "markdown_cells": 1,
                "cells": [
                    {"cell_type": "markdown", "source": "# Test", "outputs": []},
                    {"cell_type": "code", "source": "print('hello')", "outputs": []},
                ]
            }
        )

        result = runner.invoke(app, ["notebook", "read", "/test/notebook.ipynb"])
        assert result.exit_code == 0
        assert "3 cells" in result.stdout

    @patch("roura_agent.tools.notebook.read_notebook")
    def test_notebook_read_error(self, mock_read):
        """Test notebook read error handling."""
        mock_read.return_value = Mock(
            success=False,
            error="File not found"
        )

        result = runner.invoke(app, ["notebook", "read", "/nonexistent.ipynb"])
        assert result.exit_code == 1
        assert "Error" in result.stdout


class TestMemoryCommands:
    """Tests for memory subcommands."""

    @patch("roura_agent.tools.memory.store_note")
    def test_memory_store_success(self, mock_store):
        """Test memory store command."""
        mock_store.return_value = Mock(
            success=True,
            output={"id": "note-123"}
        )

        result = runner.invoke(app, ["memory", "store", "Test note content"])
        assert result.exit_code == 0
        assert "note-123" in result.stdout

    @patch("roura_agent.tools.memory.store_note")
    def test_memory_store_with_tags(self, mock_store):
        """Test memory store with tags."""
        mock_store.return_value = Mock(
            success=True,
            output={"id": "note-456"}
        )

        result = runner.invoke(app, ["memory", "store", "Test", "-t", "tag1", "-t", "tag2"])
        assert result.exit_code == 0
        mock_store.assert_called_once()
        call_kwargs = mock_store.call_args[1]
        assert "tag1" in call_kwargs["tags"]
        assert "tag2" in call_kwargs["tags"]

    @patch("roura_agent.tools.memory.recall_notes")
    def test_memory_recall_empty(self, mock_recall):
        """Test memory recall with no notes."""
        mock_recall.return_value = Mock(
            success=True,
            output={"notes": []}
        )

        result = runner.invoke(app, ["memory", "recall"])
        assert result.exit_code == 0
        assert "No notes" in result.stdout

    @patch("roura_agent.tools.memory.recall_notes")
    def test_memory_recall_with_results(self, mock_recall):
        """Test memory recall with results."""
        mock_recall.return_value = Mock(
            success=True,
            output={
                "notes": [
                    {"id": "n1", "content": "Test content", "timestamp": "2024-01-01", "tags": ["test"]},
                ]
            }
        )

        result = runner.invoke(app, ["memory", "recall"])
        assert result.exit_code == 0
        assert "Test content" in result.stdout

    @patch("roura_agent.tools.memory.clear_memory")
    def test_memory_clear_with_force(self, mock_clear):
        """Test memory clear with --force."""
        mock_clear.return_value = Mock(
            success=True,
            output={"deleted": 5}
        )

        result = runner.invoke(app, ["memory", "clear", "--force"])
        assert result.exit_code == 0
        assert "cleared" in result.stdout.lower()


class TestStatusCommand:
    """Tests for status command."""

    @patch("roura_agent.llm.detect_available_providers")
    @patch("roura_agent.tools.mcp.get_mcp_manager")
    @patch("roura_agent.config.detect_project")
    def test_status_command(self, mock_project, mock_mcp, mock_providers):
        """Test status command displays info."""
        from roura_agent.llm import ProviderType

        mock_providers.return_value = [ProviderType.OLLAMA]
        mock_manager = Mock()
        mock_manager.list_servers.return_value = []
        mock_mcp.return_value = mock_manager
        mock_project.return_value = Mock(
            name="test-project",
            type="python",
            files=[],
            git_branch="main",
        )

        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "System Status" in result.stdout
        assert "Provider" in result.stdout


class TestCompletionCommand:
    """Tests for completion command."""

    def test_completion_bash(self):
        """Test completion for bash."""
        result = runner.invoke(app, ["completion", "bash"])
        assert result.exit_code == 0
        assert "show-completion" in result.stdout

    def test_completion_zsh(self):
        """Test completion for zsh."""
        result = runner.invoke(app, ["completion", "zsh"])
        assert result.exit_code == 0
        assert "show-completion" in result.stdout

    def test_completion_invalid(self):
        """Test completion with invalid shell."""
        result = runner.invoke(app, ["completion", "invalid"])
        assert result.exit_code == 1
        assert "Unknown shell" in result.stdout


class TestHelperFunctions:
    """Tests for CLI helper functions."""

    def test_error_panel(self):
        """Test _error_panel function."""
        from roura_agent.cli import _error_panel
        # Just verify it doesn't raise
        _error_panel("Test Error", "This is a test error", "Try this instead")

    def test_success_panel(self):
        """Test _success_panel function."""
        from roura_agent.cli import _success_panel
        _success_panel("Success", "Operation completed")

    def test_warning_panel(self):
        """Test _warning_panel function."""
        from roura_agent.cli import _warning_panel
        _warning_panel("Warning", "Be careful")

    def test_info_panel(self):
        """Test _info_panel function."""
        from roura_agent.cli import _info_panel
        _info_panel("Info", "Some information")

    def test_run_with_spinner(self):
        """Test _run_with_spinner function."""
        from roura_agent.cli import _run_with_spinner

        def test_func(x, y):
            return x + y

        result = _run_with_spinner(test_func, "Testing...", 1, 2)
        assert result == 3
