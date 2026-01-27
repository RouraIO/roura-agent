# Roura Agent

[![CI](https://github.com/roura-io/roura-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/roura-io/roura-agent/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![PyPI](https://img.shields.io/pypi/v/roura-agent)](https://pypi.org/project/roura-agent/)

**Local-first AI coding assistant with multi-provider support.**

Roura Agent is a powerful terminal-based AI assistant for software development. It supports multiple LLM providers (Ollama, OpenAI, Anthropic) with native tool calling, giving you Claude Code-like capabilities with the flexibility to choose your provider.

## Quick Start

```bash
# Install
pip install roura-agent

# Run with auto-detected provider
roura-agent

# Or specify a provider
OPENAI_API_KEY=xxx roura-agent
ANTHROPIC_API_KEY=xxx roura-agent
roura-agent --provider ollama
```

## Features

### Multi-Provider Support

| Provider | Setup | Best For |
|----------|-------|----------|
| **Ollama** | Local install | Privacy, no API costs |
| **OpenAI** | API key | GPT-4 quality |
| **Anthropic** | API key | Claude quality |

Provider is auto-detected based on available credentials, or you can force one with `--provider`.

### Agentic Loop
- **Multi-turn execution** - Works iteratively until your task is complete
- **Native tool calling** - Direct integration with modern LLMs
- **Context-aware** - Tracks files you've read and modified
- **Session persistence** - Auto-saves conversations, resume with `/resume`

### 45+ Development Tools
- **File operations** - Read, write, edit files with visual diff preview
- **Git integration** - Status, diff, log, add, commit
- **Shell commands** - Execute with safety guardrails
- **Search** - Glob patterns and grep across your codebase
- **GitHub** - List, view, and create PRs and issues
- **Jira** - Search, view, create, and transition issues

### Safety & Control
- **Approval gates** - Review and approve changes before they happen
- **Visual diffs** - See exactly what will change
- **Undo support** - Restore previous file versions with `/undo`
- **Read-before-modify** - Files must be read before they can be edited
- **Secrets detection** - Blocks credential commits
- **Blast radius limits** - `--allow` and `--block` patterns
- **Dry-run mode** - Preview all changes with `--dry-run`
- **Read-only mode** - Block all modifications with `--readonly`

### User Experience
- **Rich TUI** - Beautiful terminal interface with colors and formatting
- **Streaming responses** - See output as it's generated
- **Progress indicators** - Elapsed time display during operations
- **Token tracking** - Monitor context usage

## Installation

### From PyPI (Recommended)

```bash
pip install roura-agent
```

### From Source

```bash
git clone https://github.com/roura-io/roura-agent.git
cd roura-agent
pip install -e .
```

### Provider Setup

**Option 1: Ollama (Local, Free)**
```bash
# Install Ollama from ollama.com
curl -fsSL https://ollama.com/install.sh | sh

# Pull a model
ollama pull qwen2.5-coder:32b

# Set environment
export OLLAMA_MODEL=qwen2.5-coder:32b
```

**Option 2: OpenAI**
```bash
export OPENAI_API_KEY=sk-...
export OPENAI_MODEL=gpt-4o  # optional, defaults to gpt-4o
```

**Option 3: Anthropic**
```bash
export ANTHROPIC_API_KEY=sk-ant-...
export ANTHROPIC_MODEL=claude-sonnet-4-20250514  # optional
```

## Usage

```bash
# Start in your project directory
cd /path/to/your/project
roura-agent

# Example interactions:
> Read the main entry point and explain what it does
> Fix the bug in the login function
> Add input validation to the user form
> Create a new API endpoint for user profiles
```

### CLI Options

```bash
roura-agent [OPTIONS]

Options:
  -p, --provider TEXT    LLM provider: ollama, openai, anthropic
  -s, --safe-mode        Disable dangerous tools
  -n, --dry-run          Preview changes without writing
  -r, --readonly         Block all file modifications
  -a, --allow TEXT       Only allow modifications to matching globs
  -b, --block TEXT       Block modifications to matching globs
  -d, --debug            Enable debug logging
```

### Interactive Commands

| Command | Description |
|---------|-------------|
| `/help` | Show help information |
| `/context` | Show files in context |
| `/undo` | Undo last file change |
| `/clear` | Clear conversation |
| `/tools` | List available tools |
| `/history` | Show recent sessions |
| `/resume [id]` | Resume a previous session |
| `/export [format]` | Export session (json/markdown) |
| `exit` | Quit the agent |

### Subcommands

```bash
roura-agent doctor       # Run system health checks
roura-agent setup        # Interactive configuration wizard
roura-agent config       # Show current configuration
roura-agent tools        # List all tools with risk levels
roura-agent ping         # Test Ollama connectivity
roura-agent project      # Show project information
```

## Configuration

Configuration is stored in `~/.config/roura-agent/`:

```bash
roura-agent setup  # Interactive configuration wizard
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `ROURA_PROVIDER` | Default provider | auto-detect |
| `OLLAMA_BASE_URL` | Ollama endpoint | http://localhost:11434 |
| `OLLAMA_MODEL` | Ollama model | - |
| `OPENAI_API_KEY` | OpenAI API key | - |
| `OPENAI_MODEL` | OpenAI model | gpt-4o |
| `ANTHROPIC_API_KEY` | Anthropic API key | - |
| `ANTHROPIC_MODEL` | Anthropic model | claude-sonnet-4-20250514 |

## Comparison

| Feature | Roura Agent | Claude Code | Cursor | Aider |
|---------|-------------|-------------|--------|-------|
| Multi-provider | Yes | No | Limited | Yes |
| Local LLM support | Yes | No | No | Yes |
| Privacy (local mode) | Yes | No | No | Yes |
| Native tool calling | Yes | Yes | Limited | Yes |
| Session persistence | Yes | Yes | No | Yes |
| Undo support | Yes | Yes | No | No |
| Git integration | Yes | Yes | Limited | Yes |
| GitHub/Jira | Yes | Yes | No | No |
| Safety controls | Yes | Yes | Limited | Limited |
| Free tier | Yes (Ollama) | No | No | No |

## Development

### Running Tests

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

### Code Quality

```bash
ruff check roura_agent/
pyright roura_agent/
```

## License

MIT License - See [LICENSE](LICENSE) for details.

## Support

- **Issues**: [GitHub Issues](https://github.com/roura-io/roura-agent/issues)
- **Documentation**: [docs.roura.io](https://docs.roura.io)
