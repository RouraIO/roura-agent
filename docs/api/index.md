# API Reference

This section documents the Roura Agent Python API for developers who want to:
- Extend Roura Agent with custom tools
- Integrate Roura Agent into other applications
- Understand the internal architecture

## Modules

### Core

| Module | Description |
|--------|-------------|
| [`roura_agent.agent.loop`](loop.md) | Main agentic loop implementation |
| [`roura_agent.agent.context`](context.md) | Context management and state |
| [`roura_agent.llm`](llm.md) | LLM provider abstraction |
| [`roura_agent.config`](config.md) | Configuration management |
| [`roura_agent.retry`](retry.md) | Retry and resilience patterns |
| [`roura_agent.metrics`](metrics.md) | Metrics and observability |

### Tools

| Module | Description |
|--------|-------------|
| [`roura_agent.tools.base`](tools-base.md) | Tool base classes and registry |
| [`roura_agent.tools.fs`](tools-fs.md) | File system tools |
| [`roura_agent.tools.git`](tools-git.md) | Git operations |
| [`roura_agent.tools.shell`](tools-shell.md) | Shell command execution |
| [`roura_agent.tools.glob`](tools-glob.md) | File pattern matching |
| [`roura_agent.tools.grep`](tools-grep.md) | Content search |
| [`roura_agent.tools.memory`](tools-memory.md) | Session memory |
| [`roura_agent.tools.webfetch`](tools-webfetch.md) | Web fetch and search |
| [`roura_agent.tools.testing`](tools-testing.md) | Test framework integration |
| [`roura_agent.tools.build`](tools-build.md) | Build system integration |
| [`roura_agent.tools.lint`](tools-lint.md) | Linting and formatting |

### Integrations

| Module | Description |
|--------|-------------|
| [`roura_agent.tools.jira`](tools-jira.md) | Jira integration |
| [`roura_agent.tools.github`](tools-github.md) | GitHub integration |
| [`roura_agent.tools.mcp`](mcp.md) | MCP server integration |
| [`roura_agent.tools.image`](image.md) | Image understanding |
| [`roura_agent.tools.notebook`](notebook.md) | Jupyter notebook support |

### Utilities

| Module | Description |
|--------|-------------|
| [`roura_agent.session`](session.md) | Session persistence |
| [`roura_agent.logging`](logging.md) | Structured logging |
| [`roura_agent.errors`](errors.md) | Error codes and handling |

## Quick Start

### Using the Agent Programmatically

```python
from roura_agent.agent.loop import AgentLoop, AgentConfig
from rich.console import Console

# Create agent with custom config
config = AgentConfig(
    max_iterations=30,
    require_approval_dangerous=True,
    stream_responses=True,
)

agent = AgentLoop(
    console=Console(),
    config=config,
)

# Process a request
response = agent.process("Read main.py and add type hints")
print(response)
```

### Creating Custom Tools

```python
from roura_agent.tools.base import Tool, RiskLevel, ToolResult, registry

@registry.register("custom.hello")
class HelloTool(Tool):
    """Greet the user."""

    name = "custom.hello"
    description = "Say hello to someone"
    risk_level = RiskLevel.SAFE

    parameters = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Name to greet",
            }
        },
        "required": ["name"],
    }

    def execute(self, name: str) -> ToolResult:
        return ToolResult(
            success=True,
            output={"message": f"Hello, {name}!"},
        )
```

### Using the LLM Provider Directly

```python
from roura_agent.llm import get_provider, ProviderType

# Get provider (Anthropic, OpenAI, Ollama)
provider = get_provider(ProviderType.ANTHROPIC)

# Simple chat
messages = [
    {"role": "user", "content": "Explain Python decorators"}
]

response = provider.chat(messages)
print(response.content)

# With vision (Claude 3+)
if provider.supports_vision():
    response = provider.chat_with_images(
        prompt="What's in this image?",
        images=[{"type": "base64", "data": "...", "media_type": "image/png"}],
    )
```

### Using Retry and Resilience

```python
from roura_agent.retry import retry, CircuitBreaker, with_fallback

# Automatic retry
@retry(max_attempts=3, base_delay=1.0)
def fetch_data():
    return api.call()

# Circuit breaker for external services
breaker = CircuitBreaker(failure_threshold=5)

@breaker
def call_service():
    return external_api.request()

# Fallback values
@with_fallback(fallback_value=[])
def get_items():
    return api.fetch_items()
```

### Using Metrics

```python
from roura_agent.metrics import get_metrics, track_operation

m = get_metrics()

# Track counters
m.counter("requests_total").inc()

# Track operation timing
with track_operation("api_call", endpoint="/users") as op:
    result = api.get("/users")
    op.set_result(result)
```

### Using Configuration

```python
from roura_agent.config import get_config_manager

config = get_config_manager()
config.load()

# Access typed config
model = config.llm.model
timeout = config.tools.timeout

# Get by key
api_key = config.get("llm.api_key")

# CLI overrides
config.set_cli_override("llm.model", "claude-opus-4-20250514")
```

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                     CLI (cli.py)                        │
├─────────────────────────────────────────────────────────┤
│                  AgentLoop (agent/loop.py)              │
│  ┌──────────────┐  ┌───────────────┐  ┌──────────────┐  │
│  │   Context    │  │   Summarizer  │  │   Session    │  │
│  │ (context.py) │  │(summarizer.py)│  │ (session.py) │  │
│  └──────────────┘  └───────────────┘  └──────────────┘  │
├─────────────────────────────────────────────────────────┤
│              LLM Providers (llm/)                       │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐       │
│  │Anthropic│ │ OpenAI  │ │ Ollama  │ │ Custom  │       │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘       │
├─────────────────────────────────────────────────────────┤
│                   Tool Registry                         │
│  ┌────┐ ┌────┐ ┌─────┐ ┌────┐ ┌─────┐ ┌───┐ ┌─────┐   │
│  │ fs │ │git │ │shell│ │jira│ │image│ │mcp│ │ ... │   │
│  └────┘ └────┘ └─────┘ └────┘ └─────┘ └───┘ └─────┘   │
├─────────────────────────────────────────────────────────┤
│               Support Modules                           │
│  ┌────────┐ ┌─────────┐ ┌────────┐ ┌─────────┐         │
│  │ Config │ │ Metrics │ │ Retry  │ │ Errors  │         │
│  └────────┘ └─────────┘ └────────┘ └─────────┘         │
└─────────────────────────────────────────────────────────┘
```

## Type Definitions

### Common Types

```python
from typing import Optional, Any
from dataclasses import dataclass, field
from enum import Enum

class RiskLevel(Enum):
    SAFE = "safe"
    MODERATE = "moderate"
    DANGEROUS = "dangerous"

@dataclass
class ToolResult:
    success: bool
    output: Optional[dict] = None
    error: Optional[str] = None

@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict

@dataclass
class LLMResponse:
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    done: bool = False
    error: Optional[str] = None
    interrupted: bool = False
```

## Error Handling

All errors inherit from `RouraError`:

```python
from roura_agent.errors import RouraError, ErrorCode

try:
    agent.process("do something")
except RouraError as e:
    print(f"Error {e.code.value}: {e.message}")
    print(f"Hint: {e.hint}")
```

See [Error Codes](../TROUBLESHOOTING.md) for the full list.

## Configuration

Configuration can be set via:
1. CLI flags (highest priority)
2. Environment variables
3. Project config (`.roura/config.toml`)
4. User config (`~/.config/roura/config.toml`)
5. Built-in defaults (lowest priority)

```python
from roura_agent.config import get_config_manager, ConfigSource

config = get_config_manager()
config.load()

# Check where a value came from
source = config.get_source("llm.model")
if source == ConfigSource.ENV:
    print("Model set via environment variable")
```

See [Configuration Reference](config.md) for all options.

## Feature Modules

### Retry & Resilience

Handle transient failures gracefully:
- Automatic retry with exponential backoff
- Circuit breaker for failing services
- Fallback values for degraded operation

See [Retry Module](retry.md).

### Metrics & Observability

Track application performance:
- Counters for events
- Gauges for current state
- Histograms for distributions
- Operation timing

See [Metrics Module](metrics.md).

### MCP Integration

Connect to external tool servers:
- Stdio and SSE transports
- Tool and resource discovery
- Multi-server management

See [MCP Module](mcp.md).

### Image Understanding

Analyze visual content:
- Image metadata extraction
- Vision AI analysis
- Image comparison

See [Image Module](image.md).
