"""
Roura Agent MCP (Model Context Protocol) Support.

Provides integration with MCP servers for extending tool capabilities.
See: https://modelcontextprotocol.io/

© Roura.io
"""
from __future__ import annotations

import json
import subprocess
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import RiskLevel, Tool, ToolParam, ToolResult, registry


class MCPTransportType(Enum):
    """MCP transport types."""
    STDIO = "stdio"
    HTTP = "http"
    WEBSOCKET = "websocket"


class MCPServerStatus(Enum):
    """MCP server connection status."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


@dataclass
class MCPToolDefinition:
    """Definition of an MCP tool."""
    name: str
    description: str
    parameters: Dict[str, Any]  # JSON Schema
    server_name: str

    def to_tool_params(self) -> List[ToolParam]:
        """Convert JSON schema to ToolParam list."""
        params = []
        properties = self.parameters.get("properties", {})
        required = set(self.parameters.get("required", []))

        for name, schema in properties.items():
            param_type = str  # Default to string
            type_str = schema.get("type", "string")
            if type_str == "integer":
                param_type = int
            elif type_str == "number":
                param_type = float
            elif type_str == "boolean":
                param_type = bool
            elif type_str == "array":
                param_type = list
            elif type_str == "object":
                param_type = dict

            params.append(ToolParam(
                name=name,
                type=param_type,
                description=schema.get("description", ""),
                required=name in required,
                default=schema.get("default"),
            ))

        return params


@dataclass
class MCPResourceDefinition:
    """Definition of an MCP resource."""
    uri: str
    name: str
    description: Optional[str] = None
    mime_type: Optional[str] = None


@dataclass
class MCPPromptDefinition:
    """Definition of an MCP prompt."""
    name: str
    description: Optional[str] = None
    arguments: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class MCPServerConfig:
    """Configuration for an MCP server."""
    name: str
    command: str
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    transport: MCPTransportType = MCPTransportType.STDIO
    url: Optional[str] = None  # For HTTP/WebSocket transport
    auto_start: bool = True


class MCPServer:
    """Represents a connection to an MCP server."""

    def __init__(self, config: MCPServerConfig):
        self.config = config
        self.status = MCPServerStatus.DISCONNECTED
        self._process: Optional[subprocess.Popen] = None
        self._tools: Dict[str, MCPToolDefinition] = {}
        self._resources: Dict[str, MCPResourceDefinition] = {}
        self._prompts: Dict[str, MCPPromptDefinition] = {}
        self._request_id = 0
        self._pending_requests: Dict[int, Future] = {}
        self._lock = threading.Lock()
        self._read_thread: Optional[threading.Thread] = None
        self._executor = ThreadPoolExecutor(max_workers=1)

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def tools(self) -> List[MCPToolDefinition]:
        return list(self._tools.values())

    @property
    def resources(self) -> List[MCPResourceDefinition]:
        return list(self._resources.values())

    @property
    def prompts(self) -> List[MCPPromptDefinition]:
        return list(self._prompts.values())

    def connect(self) -> bool:
        """Connect to the MCP server."""
        if self.status == MCPServerStatus.CONNECTED:
            return True

        self.status = MCPServerStatus.CONNECTING

        try:
            if self.config.transport == MCPTransportType.STDIO:
                return self._connect_stdio()
            elif self.config.transport == MCPTransportType.HTTP:
                return self._connect_http()
            else:
                self.status = MCPServerStatus.ERROR
                return False

        except Exception:
            self.status = MCPServerStatus.ERROR
            return False

    def _connect_stdio(self) -> bool:
        """Connect via stdio transport."""
        try:
            # Build environment
            env = dict(subprocess.os.environ)
            env.update(self.config.env)

            # Start the server process
            self._process = subprocess.Popen(
                [self.config.command] + self.config.args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                text=True,
                bufsize=1,
            )

            # Start read thread
            self._read_thread = threading.Thread(target=self._read_loop, daemon=True)
            self._read_thread.start()

            # Initialize the connection
            response = self._send_request("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {},
                    "resources": {},
                    "prompts": {},
                },
                "clientInfo": {
                    "name": "roura-agent",
                    "version": "1.0.0",
                },
            })

            if response and response.get("protocolVersion"):
                # Send initialized notification
                self._send_notification("initialized", {})

                # Discover capabilities
                self._discover_tools()
                self._discover_resources()
                self._discover_prompts()

                self.status = MCPServerStatus.CONNECTED
                return True

            self.status = MCPServerStatus.ERROR
            return False

        except Exception:
            self.status = MCPServerStatus.ERROR
            if self._process:
                self._process.terminate()
                self._process = None
            return False

    def _connect_http(self) -> bool:
        """Connect via HTTP transport (placeholder)."""
        # HTTP transport would use httpx for requests
        self.status = MCPServerStatus.ERROR
        return False

    def _read_loop(self) -> None:
        """Read responses from the server."""
        if not self._process or not self._process.stdout:
            return

        for line in self._process.stdout:
            try:
                message = json.loads(line.strip())
                self._handle_message(message)
            except json.JSONDecodeError:
                continue
            except Exception:
                continue

    def _handle_message(self, message: Dict[str, Any]) -> None:
        """Handle an incoming message from the server."""
        # Check if it's a response to a request
        if "id" in message:
            request_id = message["id"]
            with self._lock:
                if request_id in self._pending_requests:
                    future = self._pending_requests.pop(request_id)
                    if "error" in message:
                        future.set_exception(Exception(message["error"].get("message", "Unknown error")))
                    else:
                        future.set_result(message.get("result"))

    def _send_request(self, method: str, params: Dict[str, Any], timeout: float = 30.0) -> Optional[Dict[str, Any]]:
        """Send a request and wait for response."""
        if not self._process or not self._process.stdin:
            return None

        with self._lock:
            self._request_id += 1
            request_id = self._request_id
            future: Future = Future()
            self._pending_requests[request_id] = future

        message = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }

        try:
            self._process.stdin.write(json.dumps(message) + "\n")
            self._process.stdin.flush()
            return future.result(timeout=timeout)
        except Exception:
            with self._lock:
                self._pending_requests.pop(request_id, None)
            return None

    def _send_notification(self, method: str, params: Dict[str, Any]) -> None:
        """Send a notification (no response expected)."""
        if not self._process or not self._process.stdin:
            return

        message = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }

        try:
            self._process.stdin.write(json.dumps(message) + "\n")
            self._process.stdin.flush()
        except Exception:
            pass

    def _discover_tools(self) -> None:
        """Discover available tools from the server."""
        response = self._send_request("tools/list", {})
        if response and "tools" in response:
            for tool_data in response["tools"]:
                tool = MCPToolDefinition(
                    name=tool_data["name"],
                    description=tool_data.get("description", ""),
                    parameters=tool_data.get("inputSchema", {}),
                    server_name=self.name,
                )
                self._tools[tool.name] = tool

    def _discover_resources(self) -> None:
        """Discover available resources from the server."""
        response = self._send_request("resources/list", {})
        if response and "resources" in response:
            for res_data in response["resources"]:
                resource = MCPResourceDefinition(
                    uri=res_data["uri"],
                    name=res_data["name"],
                    description=res_data.get("description"),
                    mime_type=res_data.get("mimeType"),
                )
                self._resources[resource.uri] = resource

    def _discover_prompts(self) -> None:
        """Discover available prompts from the server."""
        response = self._send_request("prompts/list", {})
        if response and "prompts" in response:
            for prompt_data in response["prompts"]:
                prompt = MCPPromptDefinition(
                    name=prompt_data["name"],
                    description=prompt_data.get("description"),
                    arguments=prompt_data.get("arguments", []),
                )
                self._prompts[prompt.name] = prompt

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Call a tool on the server."""
        if self.status != MCPServerStatus.CONNECTED:
            raise RuntimeError(f"Server {self.name} is not connected")

        if tool_name not in self._tools:
            raise ValueError(f"Tool {tool_name} not found on server {self.name}")

        response = self._send_request("tools/call", {
            "name": tool_name,
            "arguments": arguments,
        })

        if response is None:
            raise RuntimeError(f"Failed to call tool {tool_name}")

        return response

    def read_resource(self, uri: str) -> Dict[str, Any]:
        """Read a resource from the server."""
        if self.status != MCPServerStatus.CONNECTED:
            raise RuntimeError(f"Server {self.name} is not connected")

        response = self._send_request("resources/read", {
            "uri": uri,
        })

        if response is None:
            raise RuntimeError(f"Failed to read resource {uri}")

        return response

    def get_prompt(self, name: str, arguments: Dict[str, str] = None) -> Dict[str, Any]:
        """Get a prompt from the server."""
        if self.status != MCPServerStatus.CONNECTED:
            raise RuntimeError(f"Server {self.name} is not connected")

        response = self._send_request("prompts/get", {
            "name": name,
            "arguments": arguments or {},
        })

        if response is None:
            raise RuntimeError(f"Failed to get prompt {name}")

        return response

    def disconnect(self) -> None:
        """Disconnect from the server."""
        if self._process:
            try:
                self._send_notification("exit", {})
                self._process.terminate()
                self._process.wait(timeout=5)
            except Exception:
                if self._process:
                    self._process.kill()
            finally:
                self._process = None

        self.status = MCPServerStatus.DISCONNECTED
        self._tools.clear()
        self._resources.clear()
        self._prompts.clear()


class MCPManager:
    """Manager for MCP server connections."""

    _instance: Optional[MCPManager] = None
    _lock = threading.Lock()

    def __new__(cls) -> MCPManager:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    instance = super().__new__(cls)
                    instance._initialize()
                    cls._instance = instance
        return cls._instance

    def _initialize(self) -> None:
        """Initialize the manager."""
        self._servers: Dict[str, MCPServer] = {}
        self._server_lock = threading.Lock()
        self._config_path: Optional[Path] = None

    @classmethod
    def get_instance(cls) -> MCPManager:
        """Get the singleton instance."""
        return cls()

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton (for testing)."""
        if cls._instance:
            for server in cls._instance._servers.values():
                server.disconnect()
        cls._instance = None

    def set_config_path(self, path: Path) -> None:
        """Set the path to MCP configuration file."""
        self._config_path = path

    def load_config(self, config_path: Optional[Path] = None) -> int:
        """
        Load MCP server configurations from a file.

        Args:
            config_path: Path to config file (JSON)

        Returns:
            Number of servers configured
        """
        path = config_path or self._config_path
        if not path:
            return 0

        path = Path(path)
        if not path.exists():
            return 0

        try:
            config_data = json.loads(path.read_text())
            servers_config = config_data.get("mcpServers", {})

            for name, server_data in servers_config.items():
                config = MCPServerConfig(
                    name=name,
                    command=server_data.get("command", ""),
                    args=server_data.get("args", []),
                    env=server_data.get("env", {}),
                    auto_start=server_data.get("autoStart", True),
                )

                if config.command:
                    self.add_server(config)

            return len(self._servers)

        except Exception:
            return 0

    def add_server(self, config: MCPServerConfig) -> MCPServer:
        """Add and optionally connect to an MCP server."""
        with self._server_lock:
            if config.name in self._servers:
                raise ValueError(f"Server {config.name} already exists")

            server = MCPServer(config)
            self._servers[config.name] = server

            if config.auto_start:
                server.connect()

            return server

    def remove_server(self, name: str) -> bool:
        """Remove and disconnect from an MCP server."""
        with self._server_lock:
            server = self._servers.pop(name, None)
            if server:
                server.disconnect()
                return True
            return False

    def get_server(self, name: str) -> Optional[MCPServer]:
        """Get an MCP server by name."""
        return self._servers.get(name)

    def list_servers(self) -> List[MCPServer]:
        """List all configured servers."""
        return list(self._servers.values())

    def list_all_tools(self) -> List[MCPToolDefinition]:
        """List all tools from all connected servers."""
        tools = []
        for server in self._servers.values():
            if server.status == MCPServerStatus.CONNECTED:
                tools.extend(server.tools)
        return tools

    def call_tool(self, server_name: str, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Call a tool on a specific server."""
        server = self.get_server(server_name)
        if not server:
            raise ValueError(f"Server {server_name} not found")
        return server.call_tool(tool_name, arguments)

    def get_status(self) -> Dict[str, Any]:
        """Get status of all servers."""
        return {
            "servers": {
                name: {
                    "status": server.status.value,
                    "tools_count": len(server.tools),
                    "resources_count": len(server.resources),
                    "prompts_count": len(server.prompts),
                }
                for name, server in self._servers.items()
            },
            "total_tools": sum(len(s.tools) for s in self._servers.values()),
        }

    def shutdown(self) -> None:
        """Shutdown all server connections."""
        with self._server_lock:
            for server in self._servers.values():
                server.disconnect()
            self._servers.clear()


def get_mcp_manager() -> MCPManager:
    """Get the global MCP manager instance."""
    return MCPManager.get_instance()


# Tool implementations for MCP management

@dataclass
class MCPListServersTool(Tool):
    """List configured MCP servers."""

    name: str = "mcp.servers"
    description: str = "List all configured MCP servers and their status"
    risk_level: RiskLevel = RiskLevel.SAFE
    parameters: list[ToolParam] = field(default_factory=list)

    def execute(self) -> ToolResult:
        """List all MCP servers."""
        manager = get_mcp_manager()
        status = manager.get_status()

        return ToolResult(
            success=True,
            output=status,
        )


@dataclass
class MCPListToolsTool(Tool):
    """List tools from MCP servers."""

    name: str = "mcp.tools"
    description: str = "List all available tools from MCP servers"
    risk_level: RiskLevel = RiskLevel.SAFE
    parameters: list[ToolParam] = field(default_factory=lambda: [
        ToolParam("server", str, "Server name (optional, lists all if not specified)", required=False),
    ])

    def execute(self, server: Optional[str] = None) -> ToolResult:
        """List MCP tools."""
        manager = get_mcp_manager()

        if server:
            srv = manager.get_server(server)
            if not srv:
                return ToolResult(
                    success=False,
                    output=None,
                    error=f"Server {server} not found",
                )
            tools = srv.tools
        else:
            tools = manager.list_all_tools()

        return ToolResult(
            success=True,
            output={
                "tools": [
                    {
                        "name": t.name,
                        "description": t.description,
                        "server": t.server_name,
                        "parameters": t.parameters,
                    }
                    for t in tools
                ],
                "count": len(tools),
            },
        )


@dataclass
class MCPCallToolTool(Tool):
    """Call a tool on an MCP server."""

    name: str = "mcp.call"
    description: str = "Call a tool on an MCP server"
    risk_level: RiskLevel = RiskLevel.MODERATE
    parameters: list[ToolParam] = field(default_factory=lambda: [
        ToolParam("server", str, "Server name", required=True),
        ToolParam("tool", str, "Tool name", required=True),
        ToolParam("arguments", dict, "Tool arguments", required=False, default={}),
    ])

    def execute(
        self,
        server: str,
        tool: str,
        arguments: Optional[Dict[str, Any]] = None,
    ) -> ToolResult:
        """Call an MCP tool."""
        manager = get_mcp_manager()

        try:
            result = manager.call_tool(server, tool, arguments or {})
            return ToolResult(
                success=True,
                output=result,
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output=None,
                error=str(e),
            )


@dataclass
class MCPConnectTool(Tool):
    """Connect to an MCP server."""

    name: str = "mcp.connect"
    description: str = "Connect to an MCP server"
    risk_level: RiskLevel = RiskLevel.MODERATE
    parameters: list[ToolParam] = field(default_factory=lambda: [
        ToolParam("name", str, "Server name", required=True),
        ToolParam("command", str, "Server command", required=True),
        ToolParam("args", list, "Command arguments", required=False, default=[]),
    ])

    def execute(
        self,
        name: str,
        command: str,
        args: Optional[List[str]] = None,
    ) -> ToolResult:
        """Connect to an MCP server."""
        manager = get_mcp_manager()

        try:
            config = MCPServerConfig(
                name=name,
                command=command,
                args=args or [],
                auto_start=True,
            )
            server = manager.add_server(config)

            return ToolResult(
                success=server.status == MCPServerStatus.CONNECTED,
                output={
                    "name": name,
                    "status": server.status.value,
                    "tools": len(server.tools),
                    "resources": len(server.resources),
                },
                error=None if server.status == MCPServerStatus.CONNECTED else "Failed to connect",
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output=None,
                error=str(e),
            )


@dataclass
class MCPDisconnectTool(Tool):
    """Disconnect from an MCP server."""

    name: str = "mcp.disconnect"
    description: str = "Disconnect from an MCP server"
    risk_level: RiskLevel = RiskLevel.SAFE
    parameters: list[ToolParam] = field(default_factory=lambda: [
        ToolParam("name", str, "Server name", required=True),
    ])

    def execute(self, name: str) -> ToolResult:
        """Disconnect from an MCP server."""
        manager = get_mcp_manager()

        if manager.remove_server(name):
            return ToolResult(
                success=True,
                output={"name": name, "status": "disconnected"},
            )
        else:
            return ToolResult(
                success=False,
                output=None,
                error=f"Server {name} not found",
            )


# Create and register tool instances
mcp_list_servers = MCPListServersTool()
mcp_list_tools = MCPListToolsTool()
mcp_call = MCPCallToolTool()
mcp_connect = MCPConnectTool()
mcp_disconnect = MCPDisconnectTool()

registry.register(mcp_list_servers)
registry.register(mcp_list_tools)
registry.register(mcp_call)
registry.register(mcp_connect)
registry.register(mcp_disconnect)


# Convenience functions
def list_mcp_servers() -> ToolResult:
    """List all MCP servers."""
    return mcp_list_servers.execute()


def list_mcp_tools(server: Optional[str] = None) -> ToolResult:
    """List MCP tools."""
    return mcp_list_tools.execute(server=server)


def call_mcp_tool(server: str, tool: str, arguments: Dict[str, Any] = None) -> ToolResult:
    """Call an MCP tool."""
    return mcp_call.execute(server=server, tool=tool, arguments=arguments)
