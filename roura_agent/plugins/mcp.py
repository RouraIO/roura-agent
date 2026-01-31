"""
Roura Agent MCP Server - Model Context Protocol integration.

MCP (Model Context Protocol) allows plugins to expose tools and resources
that can be consumed by AI models. This module provides:
- MCP server implementation
- Tool/resource registration
- Protocol message handling
- Client connection management

© Roura.io
"""
from __future__ import annotations

import asyncio
import json
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional, Union

from ..logging import get_logger
from .base import Plugin, PluginMetadata, PluginStatus, PluginType

logger = get_logger(__name__)


class MCPMessageType(str, Enum):
    """MCP protocol message types."""
    # Lifecycle
    INITIALIZE = "initialize"
    INITIALIZED = "initialized"
    SHUTDOWN = "shutdown"

    # Tools
    LIST_TOOLS = "tools/list"
    CALL_TOOL = "tools/call"
    TOOL_RESULT = "tools/result"

    # Resources
    LIST_RESOURCES = "resources/list"
    READ_RESOURCE = "resources/read"
    RESOURCE_CONTENT = "resources/content"

    # Prompts
    LIST_PROMPTS = "prompts/list"
    GET_PROMPT = "prompts/get"
    PROMPT_RESULT = "prompts/result"

    # Notifications
    NOTIFICATION = "notification"
    PROGRESS = "progress"
    LOG = "log"

    # Errors
    ERROR = "error"


@dataclass
class MCPTool:
    """MCP tool definition."""
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[..., Any]

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }


@dataclass
class MCPResource:
    """MCP resource definition."""
    uri: str
    name: str
    description: str = ""
    mime_type: str = "text/plain"

    def to_dict(self) -> dict:
        return {
            "uri": self.uri,
            "name": self.name,
            "description": self.description,
            "mimeType": self.mime_type,
        }


@dataclass
class MCPPrompt:
    """MCP prompt definition."""
    name: str
    description: str = ""
    arguments: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "arguments": self.arguments,
        }


@dataclass
class MCPMessage:
    """MCP protocol message."""
    jsonrpc: str = "2.0"
    id: Optional[Union[str, int]] = None
    method: Optional[str] = None
    params: Optional[dict[str, Any]] = None
    result: Optional[Any] = None
    error: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict:
        msg: dict[str, Any] = {"jsonrpc": self.jsonrpc}
        if self.id is not None:
            msg["id"] = self.id
        if self.method:
            msg["method"] = self.method
        if self.params:
            msg["params"] = self.params
        if self.result is not None:
            msg["result"] = self.result
        if self.error:
            msg["error"] = self.error
        return msg

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: dict) -> "MCPMessage":
        return cls(
            jsonrpc=data.get("jsonrpc", "2.0"),
            id=data.get("id"),
            method=data.get("method"),
            params=data.get("params"),
            result=data.get("result"),
            error=data.get("error"),
        )

    @classmethod
    def from_json(cls, data: str) -> "MCPMessage":
        return cls.from_dict(json.loads(data))

    @classmethod
    def error_response(cls, id: Union[str, int], code: int, message: str) -> "MCPMessage":
        return cls(
            id=id,
            error={"code": code, "message": message},
        )

    @classmethod
    def result_response(cls, id: Union[str, int], result: Any) -> "MCPMessage":
        return cls(id=id, result=result)


class MCPServerCapabilities:
    """MCP server capabilities."""

    def __init__(self):
        self.tools: bool = True
        self.resources: bool = True
        self.prompts: bool = True
        self.logging: bool = True

    def to_dict(self) -> dict:
        return {
            "tools": {"listChanged": True} if self.tools else None,
            "resources": {"listChanged": True, "subscribe": True} if self.resources else None,
            "prompts": {"listChanged": True} if self.prompts else None,
            "logging": {} if self.logging else None,
        }


class MCPServer(Plugin):
    """
    MCP Server implementation.

    Provides an MCP-compliant server that exposes tools, resources,
    and prompts to AI models.
    """

    def __init__(
        self,
        name: str = "roura-agent",
        version: str = "1.0.0",
        description: str = "Roura Agent MCP Server",
    ):
        super().__init__()
        self._metadata = PluginMetadata(
            name=name,
            version=version,
            description=description,
            plugin_type=PluginType.MCP_SERVER,
        )
        self._capabilities = MCPServerCapabilities()
        self._tools: dict[str, MCPTool] = {}
        self._resources: dict[str, MCPResource] = {}
        self._prompts: dict[str, MCPPrompt] = {}
        self._resource_handlers: dict[str, Callable] = {}
        self._prompt_handlers: dict[str, Callable] = {}
        self._initialized = False

    @property
    def metadata(self) -> PluginMetadata:
        return self._metadata

    # Tool management

    def register_tool(
        self,
        name: str,
        handler: Callable[..., Any],
        description: str = "",
        input_schema: Optional[dict[str, Any]] = None,
    ) -> None:
        """Register an MCP tool."""
        self._tools[name] = MCPTool(
            name=name,
            description=description,
            input_schema=input_schema or {"type": "object", "properties": {}},
            handler=handler,
        )
        logger.debug(f"Registered MCP tool: {name}")

    def unregister_tool(self, name: str) -> bool:
        """Unregister an MCP tool."""
        if name in self._tools:
            del self._tools[name]
            return True
        return False

    # Resource management

    def register_resource(
        self,
        uri: str,
        name: str,
        handler: Callable[[], str],
        description: str = "",
        mime_type: str = "text/plain",
    ) -> None:
        """Register an MCP resource."""
        self._resources[uri] = MCPResource(
            uri=uri,
            name=name,
            description=description,
            mime_type=mime_type,
        )
        self._resource_handlers[uri] = handler
        logger.debug(f"Registered MCP resource: {uri}")

    def unregister_resource(self, uri: str) -> bool:
        """Unregister an MCP resource."""
        if uri in self._resources:
            del self._resources[uri]
            del self._resource_handlers[uri]
            return True
        return False

    # Prompt management

    def register_prompt(
        self,
        name: str,
        handler: Callable[..., dict],
        description: str = "",
        arguments: Optional[list[dict]] = None,
    ) -> None:
        """Register an MCP prompt."""
        self._prompts[name] = MCPPrompt(
            name=name,
            description=description,
            arguments=arguments or [],
        )
        self._prompt_handlers[name] = handler
        logger.debug(f"Registered MCP prompt: {name}")

    def unregister_prompt(self, name: str) -> bool:
        """Unregister an MCP prompt."""
        if name in self._prompts:
            del self._prompts[name]
            del self._prompt_handlers[name]
            return True
        return False

    # Message handling

    async def handle_message(self, message: MCPMessage) -> MCPMessage:
        """Handle an incoming MCP message."""
        method = message.method
        params = message.params or {}
        msg_id = message.id

        try:
            if method == MCPMessageType.INITIALIZE:
                return await self._handle_initialize(msg_id, params)
            elif method == MCPMessageType.LIST_TOOLS:
                return await self._handle_list_tools(msg_id)
            elif method == MCPMessageType.CALL_TOOL:
                return await self._handle_call_tool(msg_id, params)
            elif method == MCPMessageType.LIST_RESOURCES:
                return await self._handle_list_resources(msg_id)
            elif method == MCPMessageType.READ_RESOURCE:
                return await self._handle_read_resource(msg_id, params)
            elif method == MCPMessageType.LIST_PROMPTS:
                return await self._handle_list_prompts(msg_id)
            elif method == MCPMessageType.GET_PROMPT:
                return await self._handle_get_prompt(msg_id, params)
            elif method == MCPMessageType.SHUTDOWN:
                return await self._handle_shutdown(msg_id)
            else:
                return MCPMessage.error_response(
                    msg_id, -32601, f"Method not found: {method}"
                )
        except Exception as e:
            logger.error(f"Error handling MCP message: {e}")
            return MCPMessage.error_response(msg_id, -32603, str(e))

    async def _handle_initialize(
        self, msg_id: Union[str, int], params: dict
    ) -> MCPMessage:
        """Handle initialize request."""
        self._initialized = True
        return MCPMessage.result_response(msg_id, {
            "protocolVersion": "2024-11-05",
            "serverInfo": {
                "name": self._metadata.name,
                "version": self._metadata.version,
            },
            "capabilities": self._capabilities.to_dict(),
        })

    async def _handle_list_tools(self, msg_id: Union[str, int]) -> MCPMessage:
        """Handle tools/list request."""
        return MCPMessage.result_response(msg_id, {
            "tools": [tool.to_dict() for tool in self._tools.values()],
        })

    async def _handle_call_tool(
        self, msg_id: Union[str, int], params: dict
    ) -> MCPMessage:
        """Handle tools/call request."""
        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        if tool_name not in self._tools:
            return MCPMessage.error_response(
                msg_id, -32602, f"Tool not found: {tool_name}"
            )

        tool = self._tools[tool_name]

        try:
            result = tool.handler(**arguments)
            if asyncio.iscoroutine(result):
                result = await result

            return MCPMessage.result_response(msg_id, {
                "content": [{"type": "text", "text": str(result)}],
                "isError": False,
            })
        except Exception as e:
            return MCPMessage.result_response(msg_id, {
                "content": [{"type": "text", "text": str(e)}],
                "isError": True,
            })

    async def _handle_list_resources(self, msg_id: Union[str, int]) -> MCPMessage:
        """Handle resources/list request."""
        return MCPMessage.result_response(msg_id, {
            "resources": [res.to_dict() for res in self._resources.values()],
        })

    async def _handle_read_resource(
        self, msg_id: Union[str, int], params: dict
    ) -> MCPMessage:
        """Handle resources/read request."""
        uri = params.get("uri")

        if uri not in self._resources:
            return MCPMessage.error_response(
                msg_id, -32602, f"Resource not found: {uri}"
            )

        handler = self._resource_handlers[uri]
        resource = self._resources[uri]

        try:
            content = handler()
            if asyncio.iscoroutine(content):
                content = await content

            return MCPMessage.result_response(msg_id, {
                "contents": [{
                    "uri": uri,
                    "mimeType": resource.mime_type,
                    "text": content,
                }],
            })
        except Exception as e:
            return MCPMessage.error_response(msg_id, -32603, str(e))

    async def _handle_list_prompts(self, msg_id: Union[str, int]) -> MCPMessage:
        """Handle prompts/list request."""
        return MCPMessage.result_response(msg_id, {
            "prompts": [prompt.to_dict() for prompt in self._prompts.values()],
        })

    async def _handle_get_prompt(
        self, msg_id: Union[str, int], params: dict
    ) -> MCPMessage:
        """Handle prompts/get request."""
        prompt_name = params.get("name")
        arguments = params.get("arguments", {})

        if prompt_name not in self._prompts:
            return MCPMessage.error_response(
                msg_id, -32602, f"Prompt not found: {prompt_name}"
            )

        handler = self._prompt_handlers[prompt_name]

        try:
            result = handler(**arguments)
            if asyncio.iscoroutine(result):
                result = await result

            return MCPMessage.result_response(msg_id, result)
        except Exception as e:
            return MCPMessage.error_response(msg_id, -32603, str(e))

    async def _handle_shutdown(self, msg_id: Union[str, int]) -> MCPMessage:
        """Handle shutdown request."""
        self._initialized = False
        return MCPMessage.result_response(msg_id, {})

    # Plugin interface

    def activate(self) -> bool:
        """Activate the MCP server."""
        self._set_status(PluginStatus.ACTIVE)
        return True

    def deactivate(self) -> bool:
        """Deactivate the MCP server."""
        self._initialized = False
        self._set_status(PluginStatus.UNLOADED)
        return True


class MCPTransport(ABC):
    """Abstract base for MCP transport."""

    @abstractmethod
    async def send(self, message: MCPMessage) -> None:
        """Send a message."""
        ...

    @abstractmethod
    async def receive(self) -> MCPMessage:
        """Receive a message."""
        ...


class MCPStdioTransport(MCPTransport):
    """MCP transport over stdio."""

    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ):
        self._reader = reader
        self._writer = writer

    async def send(self, message: MCPMessage) -> None:
        """Send a message over stdout."""
        data = message.to_json()
        # MCP uses Content-Length header
        header = f"Content-Length: {len(data)}\r\n\r\n"
        self._writer.write(header.encode() + data.encode())
        await self._writer.drain()

    async def receive(self) -> MCPMessage:
        """Receive a message from stdin."""
        # Read headers
        headers: dict[str, str] = {}
        while True:
            line = await self._reader.readline()
            line = line.decode().strip()
            if not line:
                break
            if ": " in line:
                key, value = line.split(": ", 1)
                headers[key.lower()] = value

        # Read content
        content_length = int(headers.get("content-length", 0))
        if content_length:
            data = await self._reader.read(content_length)
            return MCPMessage.from_json(data.decode())

        raise ValueError("No content received")


async def run_mcp_server(server: MCPServer) -> None:
    """Run MCP server over stdio."""
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)

    loop = asyncio.get_event_loop()
    await loop.connect_read_pipe(lambda: protocol, __import__("sys").stdin)

    writer_transport, writer_protocol = await loop.connect_write_pipe(
        lambda: asyncio.streams.FlowControlMixin(loop),
        __import__("sys").stdout,
    )
    writer = asyncio.StreamWriter(writer_transport, writer_protocol, None, loop)

    transport = MCPStdioTransport(reader, writer)

    server.activate()

    try:
        while True:
            try:
                message = await transport.receive()
                response = await server.handle_message(message)
                await transport.send(response)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"MCP server error: {e}")
    finally:
        server.deactivate()
