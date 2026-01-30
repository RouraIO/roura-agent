"""
Tests for the MCP (Model Context Protocol) support.

© Roura.io
"""
import pytest
import json
import threading
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
import tempfile

from roura_agent.tools.mcp import (
    MCPManager,
    MCPServer,
    MCPServerConfig,
    MCPServerStatus,
    MCPTransportType,
    MCPToolDefinition,
    MCPResourceDefinition,
    MCPPromptDefinition,
    MCPListServersTool,
    MCPListToolsTool,
    MCPCallToolTool,
    MCPConnectTool,
    MCPDisconnectTool,
    get_mcp_manager,
)


class TestMCPTransportType:
    """Tests for MCPTransportType enum."""

    def test_transport_types_exist(self):
        """Test all transport types exist."""
        assert MCPTransportType.STDIO.value == "stdio"
        assert MCPTransportType.HTTP.value == "http"
        assert MCPTransportType.WEBSOCKET.value == "websocket"


class TestMCPServerStatus:
    """Tests for MCPServerStatus enum."""

    def test_statuses_exist(self):
        """Test all server statuses exist."""
        assert MCPServerStatus.DISCONNECTED.value == "disconnected"
        assert MCPServerStatus.CONNECTING.value == "connecting"
        assert MCPServerStatus.CONNECTED.value == "connected"
        assert MCPServerStatus.ERROR.value == "error"


class TestMCPToolDefinition:
    """Tests for MCPToolDefinition."""

    def test_create_tool_definition(self):
        """Test creating a tool definition."""
        tool = MCPToolDefinition(
            name="test_tool",
            description="A test tool",
            parameters={
                "type": "object",
                "properties": {
                    "input": {"type": "string", "description": "Input value"},
                },
                "required": ["input"],
            },
            server_name="test_server",
        )
        assert tool.name == "test_tool"
        assert tool.description == "A test tool"
        assert tool.server_name == "test_server"

    def test_to_tool_params(self):
        """Test converting to ToolParam list."""
        tool = MCPToolDefinition(
            name="test_tool",
            description="Test",
            parameters={
                "properties": {
                    "name": {"type": "string", "description": "Name"},
                    "count": {"type": "integer", "description": "Count"},
                    "enabled": {"type": "boolean", "description": "Enabled"},
                },
                "required": ["name"],
            },
            server_name="test",
        )
        params = tool.to_tool_params()
        assert len(params) == 3

        # Check types were converted correctly
        param_map = {p.name: p for p in params}
        assert param_map["name"].type == str
        assert param_map["name"].required is True
        assert param_map["count"].type == int
        assert param_map["count"].required is False
        assert param_map["enabled"].type == bool


class TestMCPResourceDefinition:
    """Tests for MCPResourceDefinition."""

    def test_create_resource_definition(self):
        """Test creating a resource definition."""
        resource = MCPResourceDefinition(
            uri="file:///test/path.txt",
            name="Test Resource",
            description="A test resource",
            mime_type="text/plain",
        )
        assert resource.uri == "file:///test/path.txt"
        assert resource.name == "Test Resource"
        assert resource.mime_type == "text/plain"


class TestMCPPromptDefinition:
    """Tests for MCPPromptDefinition."""

    def test_create_prompt_definition(self):
        """Test creating a prompt definition."""
        prompt = MCPPromptDefinition(
            name="test_prompt",
            description="A test prompt",
            arguments=[
                {"name": "topic", "description": "Topic to discuss"},
            ],
        )
        assert prompt.name == "test_prompt"
        assert len(prompt.arguments) == 1


class TestMCPServerConfig:
    """Tests for MCPServerConfig."""

    def test_create_config(self):
        """Test creating a server config."""
        config = MCPServerConfig(
            name="test_server",
            command="python",
            args=["-m", "test_mcp_server"],
            env={"TEST_VAR": "value"},
        )
        assert config.name == "test_server"
        assert config.command == "python"
        assert config.args == ["-m", "test_mcp_server"]
        assert config.env["TEST_VAR"] == "value"
        assert config.transport == MCPTransportType.STDIO
        assert config.auto_start is True


class TestMCPServer:
    """Tests for MCPServer."""

    def test_create_server(self):
        """Test creating a server instance."""
        config = MCPServerConfig(
            name="test",
            command="echo",
        )
        server = MCPServer(config)
        assert server.name == "test"
        assert server.status == MCPServerStatus.DISCONNECTED

    def test_server_properties(self):
        """Test server property accessors."""
        config = MCPServerConfig(name="test", command="echo")
        server = MCPServer(config)

        assert server.tools == []
        assert server.resources == []
        assert server.prompts == []

    @patch("roura_agent.tools.mcp.subprocess.Popen")
    def test_connect_stdio_fails_without_response(self, mock_popen):
        """Test connection fails when server doesn't respond."""
        mock_process = Mock()
        mock_process.stdin = Mock()
        mock_process.stdout = iter([])  # No response
        mock_popen.return_value = mock_process

        config = MCPServerConfig(name="test", command="echo")
        server = MCPServer(config)

        # This should fail because no response
        result = server.connect()
        # Connection will timeout or fail
        assert server.status in (MCPServerStatus.ERROR, MCPServerStatus.CONNECTING)

    def test_disconnect(self):
        """Test disconnecting from server."""
        config = MCPServerConfig(name="test", command="echo")
        server = MCPServer(config)
        server.status = MCPServerStatus.CONNECTED

        server.disconnect()
        assert server.status == MCPServerStatus.DISCONNECTED


class TestMCPManager:
    """Tests for MCPManager."""

    @pytest.fixture(autouse=True)
    def reset_manager(self):
        """Reset the manager singleton before each test."""
        MCPManager.reset()
        yield
        MCPManager.reset()

    def test_singleton_pattern(self):
        """Test manager is a singleton."""
        m1 = MCPManager()
        m2 = MCPManager()
        assert m1 is m2

    def test_get_instance(self):
        """Test get_instance returns singleton."""
        m1 = MCPManager.get_instance()
        m2 = get_mcp_manager()
        assert m1 is m2

    def test_add_server(self):
        """Test adding a server."""
        manager = MCPManager()
        config = MCPServerConfig(
            name="test",
            command="echo",
            auto_start=False,  # Don't try to start
        )
        server = manager.add_server(config)

        assert server.name == "test"
        assert "test" in [s.name for s in manager.list_servers()]

    def test_add_duplicate_server_fails(self):
        """Test adding duplicate server raises error."""
        manager = MCPManager()
        config = MCPServerConfig(name="test", command="echo", auto_start=False)
        manager.add_server(config)

        with pytest.raises(ValueError, match="already exists"):
            manager.add_server(config)

    def test_remove_server(self):
        """Test removing a server."""
        manager = MCPManager()
        config = MCPServerConfig(name="test", command="echo", auto_start=False)
        manager.add_server(config)

        assert manager.remove_server("test") is True
        assert manager.get_server("test") is None

    def test_remove_nonexistent_server(self):
        """Test removing nonexistent server returns False."""
        manager = MCPManager()
        assert manager.remove_server("nonexistent") is False

    def test_get_server(self):
        """Test getting a server by name."""
        manager = MCPManager()
        config = MCPServerConfig(name="test", command="echo", auto_start=False)
        manager.add_server(config)

        server = manager.get_server("test")
        assert server is not None
        assert server.name == "test"

    def test_list_servers(self):
        """Test listing all servers."""
        manager = MCPManager()
        manager.add_server(MCPServerConfig(name="s1", command="echo", auto_start=False))
        manager.add_server(MCPServerConfig(name="s2", command="echo", auto_start=False))

        servers = manager.list_servers()
        assert len(servers) == 2

    def test_get_status(self):
        """Test getting status summary."""
        manager = MCPManager()
        manager.add_server(MCPServerConfig(name="test", command="echo", auto_start=False))

        status = manager.get_status()
        assert "servers" in status
        assert "test" in status["servers"]
        assert "total_tools" in status

    def test_load_config(self):
        """Test loading config from file."""
        manager = MCPManager()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            config = {
                "mcpServers": {
                    "test_server": {
                        "command": "python",
                        "args": ["-m", "test"],
                        "autoStart": False,
                    }
                }
            }
            json.dump(config, f)
            config_path = Path(f.name)

        try:
            count = manager.load_config(config_path)
            assert count == 1
            assert manager.get_server("test_server") is not None
        finally:
            config_path.unlink()

    def test_shutdown(self):
        """Test shutting down all servers."""
        manager = MCPManager()
        manager.add_server(MCPServerConfig(name="s1", command="echo", auto_start=False))
        manager.add_server(MCPServerConfig(name="s2", command="echo", auto_start=False))

        manager.shutdown()
        assert len(manager.list_servers()) == 0


class TestMCPListServersTool:
    """Tests for MCPListServersTool."""

    @pytest.fixture(autouse=True)
    def reset_manager(self):
        """Reset the manager singleton."""
        MCPManager.reset()
        yield
        MCPManager.reset()

    def test_tool_properties(self):
        """Test tool properties."""
        tool = MCPListServersTool()
        assert tool.name == "mcp.servers"
        assert tool.requires_approval is False

    def test_execute_empty(self):
        """Test executing with no servers."""
        tool = MCPListServersTool()
        result = tool.execute()
        assert result.success is True
        assert "servers" in result.output
        assert result.output["total_tools"] == 0

    def test_execute_with_servers(self):
        """Test executing with servers."""
        manager = get_mcp_manager()
        manager.add_server(MCPServerConfig(name="test", command="echo", auto_start=False))

        tool = MCPListServersTool()
        result = tool.execute()
        assert result.success is True
        assert "test" in result.output["servers"]


class TestMCPListToolsTool:
    """Tests for MCPListToolsTool."""

    @pytest.fixture(autouse=True)
    def reset_manager(self):
        """Reset the manager singleton."""
        MCPManager.reset()
        yield
        MCPManager.reset()

    def test_tool_properties(self):
        """Test tool properties."""
        tool = MCPListToolsTool()
        assert tool.name == "mcp.tools"
        assert tool.requires_approval is False

    def test_execute_no_tools(self):
        """Test executing with no tools available."""
        tool = MCPListToolsTool()
        result = tool.execute()
        assert result.success is True
        assert result.output["count"] == 0

    def test_execute_server_not_found(self):
        """Test executing with nonexistent server."""
        tool = MCPListToolsTool()
        result = tool.execute(server="nonexistent")
        assert result.success is False
        assert "not found" in result.error


class TestMCPCallToolTool:
    """Tests for MCPCallToolTool."""

    @pytest.fixture(autouse=True)
    def reset_manager(self):
        """Reset the manager singleton."""
        MCPManager.reset()
        yield
        MCPManager.reset()

    def test_tool_properties(self):
        """Test tool properties."""
        tool = MCPCallToolTool()
        assert tool.name == "mcp.call"
        assert tool.requires_approval is True  # MODERATE risk

    def test_execute_server_not_found(self):
        """Test calling tool on nonexistent server."""
        tool = MCPCallToolTool()
        result = tool.execute(server="nonexistent", tool="test")
        assert result.success is False
        assert "not found" in result.error


class TestMCPConnectTool:
    """Tests for MCPConnectTool."""

    @pytest.fixture(autouse=True)
    def reset_manager(self):
        """Reset the manager singleton."""
        MCPManager.reset()
        yield
        MCPManager.reset()

    def test_tool_properties(self):
        """Test tool properties."""
        tool = MCPConnectTool()
        assert tool.name == "mcp.connect"
        assert tool.requires_approval is True


class TestMCPDisconnectTool:
    """Tests for MCPDisconnectTool."""

    @pytest.fixture(autouse=True)
    def reset_manager(self):
        """Reset the manager singleton."""
        MCPManager.reset()
        yield
        MCPManager.reset()

    def test_tool_properties(self):
        """Test tool properties."""
        tool = MCPDisconnectTool()
        assert tool.name == "mcp.disconnect"
        assert tool.requires_approval is False

    def test_execute_not_found(self):
        """Test disconnecting from nonexistent server."""
        tool = MCPDisconnectTool()
        result = tool.execute(name="nonexistent")
        assert result.success is False
        assert "not found" in result.error

    def test_execute_success(self):
        """Test successful disconnect."""
        manager = get_mcp_manager()
        manager.add_server(MCPServerConfig(name="test", command="echo", auto_start=False))

        tool = MCPDisconnectTool()
        result = tool.execute(name="test")
        assert result.success is True
        assert result.output["status"] == "disconnected"
