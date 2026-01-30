"""
Tests for the agent loop system.

© Roura.io
"""
import pytest
from unittest.mock import Mock, MagicMock, patch, PropertyMock
import json

from roura_agent.agents.agent_loop import (
    AgentLoop,
    AgentLoopConfig,
)
from roura_agent.agents.executor import ExecutionContext, ToolPermissions
from roura_agent.agents.base import AgentContext, AgentResult
from roura_agent.tools.base import ToolResult, RiskLevel


class TestAgentLoopConfig:
    """Tests for AgentLoopConfig."""

    def test_default_values(self):
        """Test default configuration values."""
        config = AgentLoopConfig()
        assert config.max_iterations == 10
        assert config.max_tool_calls_per_turn == 5
        assert config.stream_responses is True
        assert config.show_tool_calls is True
        assert config.show_tool_results is True
        assert config.auto_approve_safe is True
        assert config.require_approval_moderate is True
        assert config.require_approval_dangerous is True

    def test_custom_values(self):
        """Test custom configuration values."""
        config = AgentLoopConfig(
            max_iterations=20,
            max_tool_calls_per_turn=10,
            stream_responses=False,
            auto_approve_safe=False,
        )
        assert config.max_iterations == 20
        assert config.max_tool_calls_per_turn == 10
        assert config.stream_responses is False
        assert config.auto_approve_safe is False


class TestAgentLoop:
    """Tests for AgentLoop."""

    @pytest.fixture
    def mock_llm(self):
        """Create a mock LLM provider."""
        llm = Mock()
        # Default response with no tool calls (ends the loop)
        llm.chat.return_value = Mock(
            content="Task completed successfully.",
            tool_calls=None,
            error=None,
            done=True,
        )
        return llm

    @pytest.fixture
    def mock_console(self):
        """Create a mock console."""
        return Mock()

    def test_create_agent_loop(self, mock_llm, mock_console):
        """Test creating an agent loop."""
        loop = AgentLoop(
            agent_name="test",
            system_prompt="You are a test agent.",
            llm=mock_llm,
            console=mock_console,
        )
        assert loop.agent_name == "test"
        assert loop.system_prompt == "You are a test agent."
        assert loop.llm is mock_llm
        assert loop.console is mock_console

    def test_allowed_tools_from_permissions(self, mock_llm, mock_console):
        """Test that allowed tools come from ToolPermissions."""
        loop = AgentLoop(
            agent_name="code",
            system_prompt="Code agent",
            llm=mock_llm,
            console=mock_console,
        )
        assert loop.allowed_tools == ToolPermissions.CODE_AGENT_TOOLS

    def test_custom_allowed_tools(self, mock_llm, mock_console):
        """Test using custom allowed tools."""
        custom_tools = {"fs.read", "fs.list"}
        loop = AgentLoop(
            agent_name="custom",
            system_prompt="Custom agent",
            llm=mock_llm,
            console=mock_console,
            allowed_tools=custom_tools,
        )
        assert loop.allowed_tools == custom_tools

    def test_execution_context_created(self, mock_llm, mock_console):
        """Test execution context is created if not provided."""
        loop = AgentLoop(
            agent_name="test",
            system_prompt="Test",
            llm=mock_llm,
            console=mock_console,
        )
        assert loop.execution_context is not None
        assert isinstance(loop.execution_context, ExecutionContext)

    def test_custom_execution_context(self, mock_llm, mock_console):
        """Test using custom execution context."""
        ctx = ExecutionContext()
        ctx.project_root = "/my/project"

        loop = AgentLoop(
            agent_name="test",
            system_prompt="Test",
            llm=mock_llm,
            console=mock_console,
            execution_context=ctx,
        )
        assert loop.execution_context is ctx
        assert loop.execution_context.project_root == "/my/project"

    def test_get_available_tools(self, mock_llm, mock_console):
        """Test getting available tools."""
        loop = AgentLoop(
            agent_name="code",
            system_prompt="Code agent",
            llm=mock_llm,
            console=mock_console,
        )
        tools = loop.get_available_tools()
        assert isinstance(tools, list)

    def test_get_tools_schema(self, mock_llm, mock_console):
        """Test getting tools schema."""
        loop = AgentLoop(
            agent_name="code",
            system_prompt="Code agent",
            llm=mock_llm,
            console=mock_console,
        )
        schema = loop.get_tools_schema()
        assert isinstance(schema, list)

    def test_execute_tool_not_allowed(self, mock_llm, mock_console):
        """Test executing a tool that's not allowed."""
        loop = AgentLoop(
            agent_name="review",  # Review agent has limited tools
            system_prompt="Review agent",
            llm=mock_llm,
            console=mock_console,
        )
        result = loop._execute_tool("shell.exec", {"command": "ls"})
        assert result["success"] is False
        assert "not allowed" in result["error"]

    def test_execute_tool_unknown(self, mock_llm, mock_console):
        """Test executing an unknown tool."""
        loop = AgentLoop(
            agent_name="code",
            system_prompt="Code agent",
            llm=mock_llm,
            console=mock_console,
            allowed_tools={"nonexistent.tool"},
        )
        result = loop._execute_tool("nonexistent.tool", {})
        assert result["success"] is False
        assert "Unknown tool" in result["error"]

    def test_run_returns_agent_result(self, mock_llm, mock_console):
        """Test that run returns an AgentResult."""
        # Mock LLM to return a simple response without tool calls
        mock_llm.chat.return_value = Mock(
            content="Done!",
            tool_calls=None,
            error=None,
            done=True,
        )

        config = AgentLoopConfig(stream_responses=False)
        loop = AgentLoop(
            agent_name="test",
            system_prompt="Test",
            llm=mock_llm,
            console=mock_console,
            config=config,
        )

        result = loop.run("Do a simple task")
        assert isinstance(result, AgentResult)
        assert result.success is True
        assert "Done!" in result.output

    def test_run_with_context(self, mock_llm, mock_console):
        """Test run with agent context."""
        mock_llm.chat.return_value = Mock(
            content="Completed",
            tool_calls=None,
            error=None,
            done=True,
        )

        config = AgentLoopConfig(stream_responses=False)
        loop = AgentLoop(
            agent_name="test",
            system_prompt="Test",
            llm=mock_llm,
            console=mock_console,
            config=config,
        )

        context = AgentContext(
            task="Test task",
            project_root="/project",
            files_in_context=["file1.py", "file2.py"],
        )

        result = loop.run("Do something", context)
        assert result.success is True
        # Verify context was used
        assert loop.execution_context.project_root == "/project"

    def test_run_respects_max_iterations(self, mock_llm, mock_console):
        """Test that run respects max iterations."""
        # Mock tool call to make loop continue
        mock_tool_call = Mock()
        mock_tool_call.id = "call_1"
        mock_tool_call.name = "fs.read"
        mock_tool_call.arguments = {"path": "/file.py"}

        # Always return tool calls to keep loop going
        mock_llm.chat.return_value = Mock(
            content="Reading...",
            tool_calls=[mock_tool_call],
            error=None,
            done=True,
        )

        config = AgentLoopConfig(max_iterations=2, stream_responses=False)
        loop = AgentLoop(
            agent_name="code",
            system_prompt="Test",
            llm=mock_llm,
            console=mock_console,
            config=config,
        )

        # Mock the tool registry to return a mock tool
        with patch("roura_agent.agents.agent_loop.tool_registry") as mock_registry:
            mock_tool = Mock()
            mock_tool.risk_level = RiskLevel.SAFE
            mock_tool.execute.return_value = ToolResult(
                success=True,
                output={"content": "file content"},
            )
            mock_registry.get.return_value = mock_tool

            result = loop.run("Read all files")

            # Should have stopped at max iterations
            assert loop._iteration <= config.max_iterations + 1

    def test_run_stops_on_llm_error(self, mock_llm, mock_console):
        """Test that run stops on LLM error."""
        mock_llm.chat.return_value = Mock(
            content=None,
            tool_calls=None,
            error="API Error",
            done=True,
        )

        config = AgentLoopConfig(stream_responses=False)
        loop = AgentLoop(
            agent_name="test",
            system_prompt="Test",
            llm=mock_llm,
            console=mock_console,
            config=config,
        )

        result = loop.run("Task")
        # Should have stopped after error
        assert loop._iteration == 1

    def test_interrupt_stops_loop(self, mock_llm, mock_console):
        """Test that interrupt stops the loop."""
        loop = AgentLoop(
            agent_name="test",
            system_prompt="Test",
            llm=mock_llm,
            console=mock_console,
        )
        loop.interrupt()
        assert loop._interrupted is True

    def test_approval_callback_called(self, mock_llm, mock_console):
        """Test that approval callback is called for moderate risk tools."""
        approval_mock = Mock(return_value=False)  # Reject approval

        loop = AgentLoop(
            agent_name="code",
            system_prompt="Test",
            llm=mock_llm,
            console=mock_console,
            approval_callback=approval_mock,
        )

        # Pre-read the file so we skip auto-read logic
        loop.execution_context.record_read("/test.py", "existing content")

        with patch("roura_agent.agents.agent_loop.tool_registry") as mock_registry:
            mock_tool = Mock()
            mock_tool.risk_level = RiskLevel.MODERATE
            mock_registry.get.return_value = mock_tool

            result = loop._execute_tool("fs.write", {"path": "/test.py"})
            assert result["success"] is False
            assert "rejected" in result["error"]
            approval_mock.assert_called_once()

    def test_safe_tools_auto_approved(self, mock_llm, mock_console):
        """Test that safe tools are auto-approved."""
        approval_mock = Mock(return_value=False)

        config = AgentLoopConfig(
            auto_approve_safe=True,
            require_approval_moderate=True,
        )
        loop = AgentLoop(
            agent_name="code",
            system_prompt="Test",
            llm=mock_llm,
            console=mock_console,
            config=config,
            approval_callback=approval_mock,
        )

        with patch("roura_agent.agents.agent_loop.tool_registry") as mock_registry:
            mock_tool = Mock()
            mock_tool.risk_level = RiskLevel.SAFE
            mock_tool.execute.return_value = ToolResult(
                success=True,
                output={"content": "file data here"}
            )
            mock_registry.get.return_value = mock_tool

            result = loop._execute_tool("fs.read", {"path": "/file.py"})
            # Should succeed without calling approval
            assert result["success"] is True
            approval_mock.assert_not_called()

    def test_display_tool_call(self, mock_llm, mock_console):
        """Test tool call display."""
        config = AgentLoopConfig(show_tool_calls=True)
        loop = AgentLoop(
            agent_name="code",
            system_prompt="Test",
            llm=mock_llm,
            console=mock_console,
            config=config,
        )

        loop._display_tool_call("fs.read", {"path": "/test.py"})
        mock_console.print.assert_called()

    def test_display_tool_call_disabled(self, mock_llm, mock_console):
        """Test tool call display when disabled."""
        config = AgentLoopConfig(show_tool_calls=False)
        loop = AgentLoop(
            agent_name="code",
            system_prompt="Test",
            llm=mock_llm,
            console=mock_console,
            config=config,
        )

        loop._display_tool_call("fs.read", {"path": "/test.py"})
        mock_console.print.assert_not_called()

    def test_display_tool_result_success(self, mock_llm, mock_console):
        """Test tool result display for success."""
        config = AgentLoopConfig(show_tool_results=True)
        loop = AgentLoop(
            agent_name="code",
            system_prompt="Test",
            llm=mock_llm,
            console=mock_console,
            config=config,
        )

        result = {"success": True, "output": {"total_lines": 10}}
        loop._display_tool_result("fs.read", result)
        mock_console.print.assert_called()

    def test_display_tool_result_error(self, mock_llm, mock_console):
        """Test tool result display for error."""
        config = AgentLoopConfig(show_tool_results=True)
        loop = AgentLoop(
            agent_name="code",
            system_prompt="Test",
            llm=mock_llm,
            console=mock_console,
            config=config,
        )

        result = {"success": False, "error": "File not found"}
        loop._display_tool_result("fs.read", result)
        mock_console.print.assert_called()

    def test_artifacts_in_result(self, mock_llm, mock_console):
        """Test that artifacts are included in result."""
        mock_llm.chat.return_value = Mock(
            content="Done",
            tool_calls=None,
            error=None,
            done=True,
        )

        config = AgentLoopConfig(stream_responses=False)
        loop = AgentLoop(
            agent_name="test",
            system_prompt="Test",
            llm=mock_llm,
            console=mock_console,
            config=config,
        )

        # Simulate some activity
        loop.execution_context.record_read("/file.py", "content")

        result = loop.run("Task")
        assert "artifacts" in result.to_dict()
        artifacts = result.artifacts
        assert "iterations" in artifacts
        assert "files_read" in artifacts
        assert "files_modified" in artifacts
        assert "tool_calls" in artifacts


class TestAgentLoopToolExecution:
    """Tests for AgentLoop tool execution specifics."""

    @pytest.fixture
    def loop_with_tools(self):
        """Create a loop with mocked tools."""
        llm = Mock()
        llm.chat.return_value = Mock(
            content="Done",
            tool_calls=None,
            error=None,
            done=True,
        )

        console = Mock()
        config = AgentLoopConfig(stream_responses=False, show_tool_calls=False, show_tool_results=False)

        return AgentLoop(
            agent_name="code",
            system_prompt="Test",
            llm=llm,
            console=console,
            config=config,
        )

    def test_read_before_write_auto_reads(self, loop_with_tools):
        """Test auto-read before write."""
        with patch("roura_agent.agents.agent_loop.tool_registry") as mock_registry:
            # Mock read tool
            mock_read = Mock()
            mock_read.execute.return_value = ToolResult(
                success=True,
                output={"content": "existing content"},
            )

            # Mock write tool
            mock_write = Mock()
            mock_write.risk_level = RiskLevel.MODERATE
            mock_write.execute.return_value = ToolResult(success=True, output={})

            def get_tool(name):
                if name == "fs.read":
                    return mock_read
                if name == "fs.write":
                    return mock_write
                return None

            mock_registry.get.side_effect = get_tool

            # File not yet read
            assert not loop_with_tools.execution_context.has_read("/new_file.py")

            # Execute write - should auto-read first
            result = loop_with_tools._execute_tool("fs.write", {"path": "/new_file.py", "content": "new"})

            # Auto-read should have been called
            mock_read.execute.assert_called()

    def test_records_tool_calls(self, loop_with_tools):
        """Test that tool calls are recorded."""
        with patch("roura_agent.agents.agent_loop.tool_registry") as mock_registry:
            mock_tool = Mock()
            mock_tool.risk_level = RiskLevel.SAFE
            mock_tool.execute.return_value = ToolResult(
                success=True,
                output={"data": "result"},
            )
            mock_registry.get.return_value = mock_tool

            loop_with_tools._execute_tool("fs.list", {"path": "/"})

            assert len(loop_with_tools.execution_context.tool_history) == 1
            assert loop_with_tools.execution_context.tool_history[0]["tool"] == "fs.list"

    def test_tracks_file_reads(self, loop_with_tools):
        """Test that file reads are tracked."""
        with patch("roura_agent.agents.agent_loop.tool_registry") as mock_registry:
            mock_tool = Mock()
            mock_tool.risk_level = RiskLevel.SAFE
            mock_tool.execute.return_value = ToolResult(
                success=True,
                output={"content": "file content here"},
            )
            mock_registry.get.return_value = mock_tool

            loop_with_tools._execute_tool("fs.read", {"path": "/test/file.py"})

            assert loop_with_tools.execution_context.has_read("/test/file.py")
