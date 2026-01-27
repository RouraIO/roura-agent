# Getting Started with Roura Agent

This tutorial walks you through your first session with Roura Agent.

## Prerequisites

- Python 3.9+
- Ollama running locally with a model installed

## Installation

```bash
pip install roura-agent
```

Or install from source:

```bash
git clone https://github.com/roura-io/roura-agent.git
cd roura-agent
pip install -e .
```

## First Run

Start Roura Agent in your project directory:

```bash
cd your-project
roura-agent chat
```

On first run, you'll see the onboarding wizard which will:
1. Detect if Ollama is running
2. List available models
3. Help you choose a model (we recommend `qwen2.5-coder:14b` or larger)

## Basic Interaction

### Reading Files

Ask Roura to read and understand code:

```
> Read the main.py file and explain what it does
```

Roura will use the `fs.read` tool to read the file and explain its contents.

### Making Changes

Ask Roura to modify code:

```
> Add a docstring to the calculate_total function in utils.py
```

Roura will:
1. Read the file first (constraint: never modify unread files)
2. Show you a diff of the proposed changes
3. Ask for approval before writing

### Running Commands

Ask Roura to run shell commands:

```
> Run the tests and show me any failures
```

For shell commands, Roura will ask for approval since they can affect your system.

## Understanding Approvals

Roura uses a risk-based approval system:

| Risk Level | Tools | Approval |
|------------|-------|----------|
| SAFE | fs.read, fs.list, git.status | Never |
| MODERATE | fs.write, fs.edit | Always |
| DANGEROUS | shell.exec, git.commit | Always |

When approval is requested, you can respond:
- `yes` or `y` - Approve this operation
- `no` or `n` - Skip this operation
- `all` - Approve all operations for this turn

## Session Commands

| Command | Description |
|---------|-------------|
| `/help` | Show available commands |
| `/context` | Show files loaded in context |
| `/undo` | Undo the last file change |
| `/clear` | Clear conversation history |
| `/tools` | List available tools |
| `/keys` | Show keyboard shortcuts |
| `/history` | View saved sessions |
| `/resume <id>` | Resume a previous session |
| `/export [json\|md]` | Export current session |
| `exit` | Quit Roura Agent |

## Keyboard Shortcuts

- **ESC** - Interrupt the current operation
- **Ctrl+C** - Cancel input (won't quit)
- **Ctrl+D** - Exit the application

## Tips for Effective Use

### Be Specific

Instead of:
```
> Fix the bug
```

Try:
```
> The calculate_discount function in pricing.py returns negative values when discount > price. Fix this by returning 0 instead.
```

### Work Iteratively

Roura works in an agentic loop. For complex tasks:
```
> First, show me the structure of the auth module
```
Then:
```
> Add a logout function to the AuthManager class
```

### Use Context

After Roura reads files, they stay in context. You can reference them:
```
> Now add similar logging to the process_payment function we looked at earlier
```

### Review Before Approving

Always review the diff preview before approving changes. Use `/undo` if something goes wrong.

## Next Steps

- [Working with Git](git-workflow.md) - Learn git integration features
- [Jira Integration](jira-integration.md) - Connect to Jira for issue tracking
- [Troubleshooting](../TROUBLESHOOTING.md) - Common issues and solutions
