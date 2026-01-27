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

### Tools

| Module | Description |
|--------|-------------|
| [`roura_agent.tools.base`](tools-base.md) | Tool base classes and registry |
| [`roura_agent.tools.fs`](tools-fs.md) | File system tools |
| [`roura_agent.tools.git`](tools-git.md) | Git operations |
| [`roura_agent.tools.shell`](tools-shell.md) | Shell command execution |
| [`roura_agent.tools.jira`](tools-jira.md) | Jira integration |

### Utilities

| Module | Description |
|--------|-------------|
| [`roura_agent.config`](config.md) | Configuration management |
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
from roura_agent.llm import OllamaProvider

provider = OllamaProvider(model_name="qwen2.5-coder:14b")

# Simple chat
messages = [
    {"role": "user", "content": "Explain Python decorators"}
]

for response in provider.chat_stream(messages, tools=None):
    if response.content:
        print(response.content, end="", flush=True)
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
│              LLM Provider (llm/ollama.py)               │
├─────────────────────────────────────────────────────────┤
│                   Tool Registry                         │
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌───────┐  │
│  │   fs   │ │  git   │ │ shell  │ │  jira  │ │ ...   │  │
│  └────────┘ └────────┘ └────────┘ └────────┘ └───────┘  │
└─────────────────────────────────────────────────────────┘
```

## Type Definitions

### Common Types

```python
from typing import Optional, Any
from dataclasses import dataclass
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
1. Config file (`~/.config/roura-agent/config.json`)
2. Environment variables
3. Programmatic override

```python
from roura_agent.config import load_config, Config

# Load existing config
config = load_config()

# Or create custom config
config = Config()
config.ollama.model = "llama3.1:8b"
config.agent.max_tool_calls = 5
```

See [Configuration Reference](config.md) for all options.
