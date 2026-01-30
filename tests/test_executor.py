"""
Tests for the agent tool executor system.

© Roura.io
"""
import pytest
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
import tempfile
import os

from roura_agent.agents.executor import (
    FileContext,
    ExecutionContext,
    ToolPermissions,
    ToolExecutorMixin,
)
from roura_agent.tools.base import ToolResult, RiskLevel


class TestFileContext:
    """Tests for FileContext dataclass."""

    def test_create_file_context(self):
        """Test creating a file context."""
        ctx = FileContext(
            path="/path/to/file.py",
            content="print('hello')",
            lines=1,
            size=14,
        )
        assert ctx.path == "/path/to/file.py"
        assert ctx.content == "print('hello')"
        assert ctx.lines == 1
        assert ctx.size == 14


class TestExecutionContext:
    """Tests for ExecutionContext."""

    def test_create_context(self):
        """Test creating an execution context."""
        ctx = ExecutionContext()
        assert ctx.files_read == {}
        assert ctx.files_modified == []
        assert ctx.tool_history == []
        assert ctx.project_root is None

    def test_record_read(self):
        """Test recording a file read."""
        ctx = ExecutionContext()
        ctx.record_read("/path/to/file.py", "line1\nline2\nline3")

        resolved = str(Path("/path/to/file.py").resolve())
        assert resolved in ctx.files_read
        file_ctx = ctx.files_read[resolved]
        assert file_ctx.lines == 3
        assert "line1" in file_ctx.content

    def test_has_read_returns_true(self):
        """Test has_read returns True for read files."""
        ctx = ExecutionContext()
        ctx.record_read("/some/file.py", "content")

        assert ctx.has_read("/some/file.py") is True

    def test_has_read_returns_false(self):
        """Test has_read returns False for unread files."""
        ctx = ExecutionContext()
        assert ctx.has_read("/unread/file.py") is False

    def test_record_modification(self):
        """Test recording a file modification."""
        ctx = ExecutionContext()
        ctx.record_modification(
            path="/path/to/file.py",
            old_content="old content",
            new_content="new content",
            action="modified",
        )

        assert len(ctx.files_modified) == 1
        mod = ctx.files_modified[0]
        assert mod["old_content"] == "old content"
        assert mod["new_content"] == "new content"
        assert mod["action"] == "modified"

    def test_record_tool_call(self):
        """Test recording a tool call."""
        ctx = ExecutionContext()
        result = ToolResult(success=True, output={"test": "data"})
        ctx.record_tool_call("fs.read", {"path": "/file.py"}, result)

        assert len(ctx.tool_history) == 1
        entry = ctx.tool_history[0]
        assert entry["tool"] == "fs.read"
        assert entry["args"]["path"] == "/file.py"
        assert entry["success"] is True

    def test_record_failed_tool_call(self):
        """Test recording a failed tool call."""
        ctx = ExecutionContext()
        result = ToolResult(success=False, output=None, error="Something failed")
        ctx.record_tool_call("fs.write", {"path": "/file.py"}, result)

        assert len(ctx.tool_history) == 1
        entry = ctx.tool_history[0]
        assert entry["success"] is False
        assert entry["error"] == "Something failed"


class TestToolPermissions:
    """Tests for ToolPermissions class."""

    def test_code_agent_tools(self):
        """Test code agent has expected tools."""
        tools = ToolPermissions.CODE_AGENT_TOOLS
        assert "fs.read" in tools
        assert "fs.write" in tools
        assert "fs.edit" in tools
        assert "glob.find" in tools
        # Code agent should NOT have shell
        assert "shell.exec" not in tools

    def test_test_agent_tools(self):
        """Test test agent has expected tools."""
        tools = ToolPermissions.TEST_AGENT_TOOLS
        assert "fs.read" in tools
        assert "fs.write" in tools
        assert "shell.exec" in tools  # Test agent can run tests

    def test_debug_agent_tools(self):
        """Test debug agent has expected tools."""
        tools = ToolPermissions.DEBUG_AGENT_TOOLS
        assert "fs.read" in tools
        assert "fs.edit" in tools
        assert "shell.exec" in tools
        # Debug agent should NOT be able to write new files
        assert "fs.write" not in tools

    def test_git_agent_tools(self):
        """Test git agent has expected tools."""
        tools = ToolPermissions.GIT_AGENT_TOOLS
        assert "git.status" in tools
        assert "git.diff" in tools
        assert "git.add" in tools
        assert "git.commit" in tools
        # Git agent should NOT write files directly
        assert "fs.write" not in tools

    def test_review_agent_tools(self):
        """Test review agent has read-only tools."""
        tools = ToolPermissions.REVIEW_AGENT_TOOLS
        assert "fs.read" in tools
        assert "grep.search" in tools
        # Review agent should NOT be able to modify
        assert "fs.write" not in tools
        assert "fs.edit" not in tools
        assert "shell.exec" not in tools

    def test_research_agent_tools(self):
        """Test research agent has web access."""
        tools = ToolPermissions.RESEARCH_AGENT_TOOLS
        assert "fs.read" in tools
        assert "web.fetch" in tools
        assert "web.search" in tools
        # Research agent should NOT modify files
        assert "fs.write" not in tools

    def test_get_for_agent_returns_correct_tools(self):
        """Test get_for_agent returns correct permission set."""
        assert ToolPermissions.get_for_agent("code") == ToolPermissions.CODE_AGENT_TOOLS
        assert ToolPermissions.get_for_agent("test") == ToolPermissions.TEST_AGENT_TOOLS
        assert ToolPermissions.get_for_agent("debug") == ToolPermissions.DEBUG_AGENT_TOOLS
        assert ToolPermissions.get_for_agent("git") == ToolPermissions.GIT_AGENT_TOOLS
        assert ToolPermissions.get_for_agent("review") == ToolPermissions.REVIEW_AGENT_TOOLS
        assert ToolPermissions.get_for_agent("research") == ToolPermissions.RESEARCH_AGENT_TOOLS

    def test_get_for_unknown_agent(self):
        """Test unknown agent gets code agent tools by default."""
        tools = ToolPermissions.get_for_agent("unknown_agent")
        assert tools == ToolPermissions.CODE_AGENT_TOOLS


class TestToolExecutorMixin:
    """Tests for ToolExecutorMixin."""

    def test_init_tool_executor(self):
        """Test initializing the tool executor."""
        class TestExecutor(ToolExecutorMixin):
            name = "test"

        executor = TestExecutor()
        executor.init_tool_executor()

        assert executor._exec_context is not None
        assert isinstance(executor._allowed_tools, set)
        assert executor._max_iterations == 10

    def test_init_with_custom_context(self):
        """Test initializing with custom context."""
        class TestExecutor(ToolExecutorMixin):
            name = "code"

        ctx = ExecutionContext()
        ctx.project_root = "/custom/root"

        executor = TestExecutor()
        executor.init_tool_executor(context=ctx)

        assert executor._exec_context is ctx
        assert executor._exec_context.project_root == "/custom/root"

    def test_init_with_custom_tools(self):
        """Test initializing with custom allowed tools."""
        class TestExecutor(ToolExecutorMixin):
            name = "code"

        custom_tools = {"fs.read", "fs.list"}
        executor = TestExecutor()
        executor.init_tool_executor(allowed_tools=custom_tools)

        assert executor._allowed_tools == custom_tools

    def test_can_use_tool_allowed(self):
        """Test can_use_tool returns True for allowed tools."""
        class TestExecutor(ToolExecutorMixin):
            name = "code"

        executor = TestExecutor()
        executor.init_tool_executor(allowed_tools={"fs.read", "fs.write"})

        assert executor.can_use_tool("fs.read") is True
        assert executor.can_use_tool("fs.write") is True

    def test_can_use_tool_not_allowed(self):
        """Test can_use_tool returns False for disallowed tools."""
        class TestExecutor(ToolExecutorMixin):
            name = "review"

        executor = TestExecutor()
        executor.init_tool_executor(allowed_tools={"fs.read"})

        assert executor.can_use_tool("shell.exec") is False
        assert executor.can_use_tool("fs.write") is False

    def test_execute_tool_not_allowed(self):
        """Test executing a disallowed tool returns error."""
        class TestExecutor(ToolExecutorMixin):
            name = "review"

        executor = TestExecutor()
        executor.init_tool_executor(allowed_tools={"fs.read"})

        result = executor.execute_tool("shell.exec", command="ls")
        assert result.success is False
        assert "not allowed" in result.error

    def test_execute_tool_unknown(self):
        """Test executing an unknown tool returns error."""
        class TestExecutor(ToolExecutorMixin):
            name = "code"

        executor = TestExecutor()
        executor.init_tool_executor(allowed_tools={"nonexistent.tool"})

        result = executor.execute_tool("nonexistent.tool")
        assert result.success is False
        assert "Unknown tool" in result.error

    def test_execute_tool_with_approval_callback(self):
        """Test tool execution with approval callback."""
        class TestExecutor(ToolExecutorMixin):
            name = "code"

        # Mock approval callback that rejects
        def reject_approval(tool_name, args):
            return False

        executor = TestExecutor()
        executor.init_tool_executor(
            allowed_tools={"fs.write"},
            approval_callback=reject_approval,
        )

        # Mock the tool and registry
        with patch("roura_agent.agents.executor.tool_registry") as mock_registry:
            mock_tool = Mock()
            mock_tool.risk_level = RiskLevel.MODERATE
            mock_registry.get.return_value = mock_tool

            result = executor.execute_tool("fs.write", path="/test.py", content="x")
            assert result.success is False
            assert "rejected" in result.error

    def test_get_default_tools_based_on_name(self):
        """Test that default tools are based on agent name."""
        class CodeExecutor(ToolExecutorMixin):
            name = "code"

        class TestExecutor(ToolExecutorMixin):
            name = "test"

        code_executor = CodeExecutor()
        code_executor.init_tool_executor()

        test_executor = TestExecutor()
        test_executor.init_tool_executor()

        # Code agent doesn't have shell.exec by default
        assert "shell.exec" not in code_executor._allowed_tools
        # Test agent does have shell.exec
        assert "shell.exec" in test_executor._allowed_tools

    def test_format_tool_result_success(self):
        """Test formatting successful tool result."""
        class TestExecutor(ToolExecutorMixin):
            name = "code"

        executor = TestExecutor()
        executor.init_tool_executor()

        result = ToolResult(success=True, output={"content": "file data"})
        formatted = executor.format_tool_result_for_llm("fs.read", result)
        assert "content" in formatted
        assert "file data" in formatted

    def test_format_tool_result_error(self):
        """Test formatting error tool result."""
        class TestExecutor(ToolExecutorMixin):
            name = "code"

        executor = TestExecutor()
        executor.init_tool_executor()

        result = ToolResult(success=False, output=None, error="File not found")
        formatted = executor.format_tool_result_for_llm("fs.read", result)
        assert "Error" in formatted
        assert "File not found" in formatted


class TestToolExecutorMixinWithRealTools:
    """Integration tests using real tools (when available)."""

    def test_get_available_tools_returns_tools(self):
        """Test getting available tools."""
        class TestExecutor(ToolExecutorMixin):
            name = "code"

        executor = TestExecutor()
        executor.init_tool_executor()

        tools = executor.get_available_tools()
        # Should return list of Tool objects
        assert isinstance(tools, list)

    def test_get_tools_schema_returns_schema(self):
        """Test getting tools JSON schema."""
        class TestExecutor(ToolExecutorMixin):
            name = "code"

        executor = TestExecutor()
        executor.init_tool_executor()

        schema = executor.get_tools_schema()
        assert isinstance(schema, list)
        # Each entry should have function format
        for entry in schema:
            if entry:  # If there are registered tools
                assert "type" in entry or "function" in entry
