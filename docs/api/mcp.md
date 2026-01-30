# MCP Server Integration

The `roura_agent.tools.mcp` module provides integration with Model Context Protocol (MCP) servers, allowing Roura Agent to use external tools and resources.

## Overview

MCP (Model Context Protocol) is a standard for connecting AI assistants to external tools and data sources. Roura Agent can:

- Connect to MCP servers (stdio or SSE transport)
- Discover and call tools provided by servers
- Access resources and prompts from servers
- Manage multiple server connections

## Quick Start

### CLI Usage

```bash
# List configured servers
roura-agent mcp servers

# List tools from all connected servers
roura-agent mcp tools

# Connect to a server
roura-agent mcp connect my-server

# Disconnect from a server
roura-agent mcp disconnect my-server
```

### Programmatic Usage

```python
from roura_agent.tools.mcp import get_mcp_manager, MCPServerConfig

# Get the MCP manager
manager = get_mcp_manager()

# Add a server configuration
config = MCPServerConfig(
    name="filesystem",
    command="npx",
    args=["-y", "@anthropic/mcp-server-fs", "/home/user/projects"],
    transport="stdio",
)
manager.add_server(config)

# Connect and list tools
await manager.connect("filesystem")
tools = await manager.list_tools("filesystem")

for tool in tools:
    print(f"{tool.name}: {tool.description}")

# Call a tool
result = await manager.call_tool(
    server_name="filesystem",
    tool_name="read_file",
    arguments={"path": "/home/user/projects/README.md"},
)
print(result)
```

## Server Configuration

### MCPServerConfig

```python
from roura_agent.tools.mcp import MCPServerConfig, MCPTransportType

config = MCPServerConfig(
    name="my-server",                # Unique identifier
    command="python",                # Command to run
    args=["-m", "my_mcp_server"],    # Command arguments
    env={"API_KEY": "secret"},       # Environment variables
    transport=MCPTransportType.STDIO,# Transport type
    timeout=30.0,                    # Connection timeout
    auto_connect=True,               # Connect on startup
)
```

### Transport Types

```python
from roura_agent.tools.mcp import MCPTransportType

MCPTransportType.STDIO  # Standard input/output (most common)
MCPTransportType.SSE    # Server-Sent Events (HTTP)
```

### Configuration File

Add servers to your config file:

```toml
# .roura/config.toml or ~/.config/roura/config.toml

[mcp]
enabled = true
timeout = 30.0
auto_connect = ["filesystem", "git"]

[mcp.servers.filesystem]
command = "npx"
args = ["-y", "@anthropic/mcp-server-fs", "/projects"]
transport = "stdio"

[mcp.servers.git]
command = "npx"
args = ["-y", "@anthropic/mcp-server-git"]
transport = "stdio"
```

## MCPManager

The central manager for all MCP server connections.

```python
from roura_agent.tools.mcp import MCPManager, get_mcp_manager

# Get singleton manager
manager = get_mcp_manager()

# Or create a new instance
manager = MCPManager()
```

### Methods

```python
# Add server configuration
manager.add_server(config: MCPServerConfig)

# Remove server
manager.remove_server(name: str)

# Connect to server
await manager.connect(name: str)

# Disconnect from server
await manager.disconnect(name: str)

# Get server status
status = manager.get_server_status(name: str)

# List all servers
servers = manager.list_servers()

# List tools from a server
tools = await manager.list_tools(server_name: str)

# List all tools from all connected servers
all_tools = await manager.list_all_tools()

# Call a tool
result = await manager.call_tool(
    server_name: str,
    tool_name: str,
    arguments: dict,
)

# List resources from a server
resources = await manager.list_resources(server_name: str)

# Read a resource
content = await manager.read_resource(
    server_name: str,
    uri: str,
)
```

## Server Status

```python
from roura_agent.tools.mcp import MCPServerStatus

class MCPServerStatus(Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"
```

## Tool Definitions

Tools discovered from MCP servers.

```python
from roura_agent.tools.mcp import MCPToolDefinition

@dataclass
class MCPToolDefinition:
    name: str                  # Tool name
    description: str           # Tool description
    input_schema: dict         # JSON Schema for parameters
    server_name: str           # Source server
```

## Resource Definitions

Resources available from MCP servers.

```python
from roura_agent.tools.mcp import MCPResourceDefinition

@dataclass
class MCPResourceDefinition:
    uri: str                   # Resource URI
    name: str                  # Resource name
    description: str           # Resource description
    mime_type: str             # Content type
    server_name: str           # Source server
```

## Built-in MCP Tools

Roura Agent provides tools for interacting with MCP servers.

### MCPListServersTool

List all configured MCP servers.

```python
from roura_agent.tools.mcp import list_mcp_servers

result = list_mcp_servers()
# Returns list of server configurations and statuses
```

### MCPListToolsTool

List available tools from MCP servers.

```python
from roura_agent.tools.mcp import list_mcp_tools

# All tools from all servers
tools = await list_mcp_tools()

# Tools from specific server
tools = await list_mcp_tools(server_name="filesystem")
```

### MCPCallToolTool

Call a tool on an MCP server.

```python
from roura_agent.tools.mcp import call_mcp_tool

result = await call_mcp_tool(
    server_name="filesystem",
    tool_name="read_file",
    arguments={"path": "/path/to/file"},
)
```

### MCPConnectTool

Connect to an MCP server.

```python
from roura_agent.tools.mcp import MCPConnectTool

tool = MCPConnectTool()
result = await tool.execute(server_name="my-server")
```

### MCPDisconnectTool

Disconnect from an MCP server.

```python
from roura_agent.tools.mcp import MCPDisconnectTool

tool = MCPDisconnectTool()
result = await tool.execute(server_name="my-server")
```

## Error Handling

```python
from roura_agent.tools.mcp import MCPError

try:
    await manager.connect("unknown-server")
except MCPError as e:
    print(f"MCP error: {e}")

try:
    result = await manager.call_tool("server", "unknown_tool", {})
except MCPError as e:
    print(f"Tool call failed: {e}")
```

## Common MCP Servers

### Filesystem Server

```toml
[mcp.servers.filesystem]
command = "npx"
args = ["-y", "@anthropic/mcp-server-fs", "/allowed/path"]
```

### Git Server

```toml
[mcp.servers.git]
command = "npx"
args = ["-y", "@anthropic/mcp-server-git"]
```

### GitHub Server

```toml
[mcp.servers.github]
command = "npx"
args = ["-y", "@anthropic/mcp-server-github"]
env = { GITHUB_TOKEN = "ghp_xxxx" }
```

### PostgreSQL Server

```toml
[mcp.servers.postgres]
command = "npx"
args = ["-y", "@anthropic/mcp-server-postgres"]
env = { DATABASE_URL = "postgresql://..." }
```

## Best Practices

### 1. Use Timeouts

```python
config = MCPServerConfig(
    name="slow-server",
    command="python",
    args=["slow_server.py"],
    timeout=60.0,  # Longer timeout for slow servers
)
```

### 2. Handle Disconnections

```python
async def safe_call(manager, server, tool, args):
    status = manager.get_server_status(server)
    if status != MCPServerStatus.CONNECTED:
        await manager.connect(server)
    return await manager.call_tool(server, tool, args)
```

### 3. Environment Variables for Secrets

```toml
[mcp.servers.api]
command = "python"
args = ["api_server.py"]
env = { API_KEY = "${API_KEY}" }  # From environment
```

### 4. Auto-Connect Important Servers

```toml
[mcp]
auto_connect = ["filesystem", "git"]
```

## API Reference

### Classes

| Class | Description |
|-------|-------------|
| `MCPManager` | Central MCP server manager |
| `MCPServer` | Individual server connection |
| `MCPServerConfig` | Server configuration |
| `MCPServerStatus` | Server connection status |
| `MCPTransportType` | Transport protocol type |
| `MCPToolDefinition` | Tool discovered from server |
| `MCPResourceDefinition` | Resource from server |
| `MCPPromptDefinition` | Prompt template from server |

### Tools

| Tool | Description |
|------|-------------|
| `MCPListServersTool` | List configured servers |
| `MCPListToolsTool` | List available tools |
| `MCPCallToolTool` | Call a server tool |
| `MCPConnectTool` | Connect to server |
| `MCPDisconnectTool` | Disconnect from server |

### Functions

| Function | Description |
|----------|-------------|
| `get_mcp_manager()` | Get singleton manager |
| `list_mcp_servers()` | List all servers |
| `list_mcp_tools()` | List all tools |
| `call_mcp_tool()` | Call a tool |
