# Roura Agent — Architecture Design Document

**Version**: 0.2.0
**Date**: 2026-01-23
**Status**: APPROVED

---

## 1. Overview

Roura Agent is a local-first, repo-native, safety-gated AI coding CLI. It executes a deterministic work loop where every mutation (file write, command execution, git operation) requires explicit user approval.

### Design Principles

| Principle | Implication |
|-----------|-------------|
| **Local-first** | All processing happens locally; LLM backend is self-hosted (Ollama) |
| **Repo-native** | Agent is always aware of git root, branch, status, and history |
| **Safety-gated** | No mutations without explicit approval |
| **Deterministic** | Same inputs → same plan (LLM temperature = 0) |
| **Auditable** | All actions logged with full context |
| **Minimal** | Do one thing well; no feature bloat |

---

## 2. CLI Command Structure

```
roura-agent
├── init              # Initialize .roura/ config in repo
├── config            # View/set configuration
│   ├── get <key>
│   ├── set <key> <value>
│   └── list
├── status            # Show agent state (repo, model, pending actions)
├── run <task>        # Execute a task with full agent loop
├── chat              # Interactive REPL (current `repl` command)
├── tools             # List available tools
│   └── list
├── history           # View session history
│   ├── list
│   └── show <id>
└── version           # Show version info
```

### Command Behavior

| Command | Mutates Repo? | Requires Approval? |
|---------|---------------|-------------------|
| `init` | Yes (.roura/) | No (explicit action) |
| `config set` | Yes (.roura/config.toml) | No (explicit action) |
| `run <task>` | Potentially | Yes (gated) |
| `chat` | Potentially | Yes (gated) |
| Others | No | No |

---

## 3. Agent Loop Design

The agent executes a finite state machine with explicit approval gates.

```
┌─────────────────────────────────────────────────────────────────┐
│                         AGENT LOOP                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   ┌──────────┐    ┌──────────┐    ┌──────────┐                 │
│   │  INSPECT │───▶│ ANALYZE  │───▶│  PLAN    │                 │
│   └──────────┘    └──────────┘    └──────────┘                 │
│        ▲                               │                        │
│        │                               ▼                        │
│        │                         ┌──────────┐                   │
│        │                         │ PROPOSE  │                   │
│        │                         └──────────┘                   │
│        │                               │                        │
│        │                               ▼                        │
│        │                    ┌─────────────────────┐             │
│        │                    │   AWAIT APPROVAL    │             │
│        │                    │  (APPROVE_ACTION?)  │             │
│        │                    └─────────────────────┘             │
│        │                         │           │                  │
│        │                    [yes]│           │[no]              │
│        │                         ▼           ▼                  │
│        │                   ┌──────────┐  ┌──────────┐           │
│        │                   │ EXECUTE  │  │  ABORT   │           │
│        │                   └──────────┘  └──────────┘           │
│        │                         │                              │
│        │                         ▼                              │
│        │                   ┌──────────┐                         │
│        │                   │  VERIFY  │                         │
│        │                   └──────────┘                         │
│        │                         │                              │
│        │                         ▼                              │
│        │                   ┌──────────┐                         │
│        │                   │  REPORT  │──────▶ [task complete?] │
│        │                   └──────────┘              │          │
│        │                                        [no] │          │
│        └─────────────────────────────────────────────┘          │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### State Definitions

| State | Description | Output |
|-------|-------------|--------|
| **INSPECT** | Read repo state, relevant files, git status | Context object |
| **ANALYZE** | LLM interprets context and user task | Understanding summary |
| **PLAN** | LLM generates plan with discrete steps | Step list |
| **PROPOSE** | Present single next action to user | Action proposal |
| **AWAIT_APPROVAL** | Block until user responds | yes/no/abort |
| **EXECUTE** | Run the approved action via tool | Tool result |
| **VERIFY** | Check action succeeded, capture output | Verification result |
| **REPORT** | Show diff/status/result to user | Summary |
| **ABORT** | Cancel current action, preserve state | Abort message |

### Loop Invariants

1. Only ONE action proposed per iteration
2. No mutation without approval
3. All state transitions logged
4. Loop terminates on: task complete, user abort, max iterations, or error

---

## 4. Tool System Design

Tools are the agent's hands. Each tool has a schema, execution logic, and risk classification.

### Tool Categories

```
tools/
├── fs/           # Filesystem operations
│   ├── read      # Read file contents
│   ├── write     # Write/overwrite file
│   ├── edit      # Patch file (search/replace)
│   ├── list      # List directory contents
│   └── delete    # Delete file
├── git/          # Git operations
│   ├── status    # git status
│   ├── diff      # git diff
│   ├── log       # git log
│   ├── add       # git add
│   ├── commit    # git commit
│   ├── branch    # git branch operations
│   └── checkout  # git checkout
├── shell/        # Shell execution
│   └── exec      # Run arbitrary command
└── jira/         # Jira integration (future)
    ├── get       # Get issue details
    ├── comment   # Add comment
    └── transition# Change issue status
```

### Tool Schema

Each tool is defined by a Pydantic model:

```
Tool:
  name: str                    # Unique identifier (e.g., "fs.write")
  description: str             # Human-readable description
  parameters: dict[str, Param] # Input parameters with types
  risk_level: RiskLevel        # safe | moderate | dangerous
  requires_approval: bool      # Derived from risk_level
  execute: Callable            # Implementation
```

### Risk Classification

| Risk Level | Requires Approval | Examples |
|------------|-------------------|----------|
| **safe** | No | fs.read, fs.list, git.status, git.diff, git.log |
| **moderate** | Yes | fs.write, fs.edit, git.add, git.commit |
| **dangerous** | Yes + confirmation | fs.delete, shell.exec, git.checkout, git.push |

### Tool Invocation Flow

```
1. LLM generates tool call: { "tool": "fs.write", "params": {...} }
2. Agent validates params against schema
3. Agent checks risk_level
4. If requires_approval: present to user, await approval
5. If approved: execute tool
6. Capture result (success/failure + output)
7. Return result to LLM for next iteration
```

---

## 5. Approval Gating Model

All mutations are gated. The approval system is the core safety mechanism.

### Approval Types

| Gate | Trigger | User Prompt |
|------|---------|-------------|
| **APPROVE_READ** | Never (reads are safe) | — |
| **APPROVE_WRITE** | fs.write, fs.edit | "Write to {path}?" |
| **APPROVE_DELETE** | fs.delete | "DELETE {path}? (irreversible)" |
| **APPROVE_COMMAND** | shell.exec | "Run: {command}?" |
| **APPROVE_GIT** | git.add, git.commit, git.checkout | "Git: {operation}?" |
| **APPROVE_COMMIT** | After staged changes | "Commit with message: {msg}?" |

### Approval Response Options

| Response | Effect |
|----------|--------|
| `yes` / `y` | Execute the action |
| `no` / `n` | Skip this action, continue loop |
| `abort` / `a` | Terminate the entire session |
| `edit` / `e` | Modify the proposed action (future) |

### Batch Approval (Future)

For experienced users, allow pre-approving categories:
```
roura-agent run --approve=fs.write,git.add "implement feature X"
```

---

## 6. Memory Model

Memory enables multi-turn conversations and cross-session context.

### Memory Layers

```
┌─────────────────────────────────────────────┐
│              MEMORY HIERARCHY               │
├─────────────────────────────────────────────┤
│                                             │
│  ┌─────────────────────────────────────┐    │
│  │         SESSION MEMORY              │    │
│  │  (conversation history, this run)   │    │
│  │  - User messages                    │    │
│  │  - Agent responses                  │    │
│  │  - Tool calls + results             │    │
│  │  Lifetime: single session           │    │
│  └─────────────────────────────────────┘    │
│                    │                        │
│                    ▼                        │
│  ┌─────────────────────────────────────┐    │
│  │         CONTEXT MEMORY              │    │
│  │  (repo state, injected each turn)   │    │
│  │  - Current working directory        │    │
│  │  - Git branch + status              │    │
│  │  - Recently read files              │    │
│  │  Lifetime: refreshed each turn      │    │
│  └─────────────────────────────────────┘    │
│                    │                        │
│                    ▼                        │
│  ┌─────────────────────────────────────┐    │
│  │        PERSISTENT MEMORY            │    │
│  │  (cross-session, stored in .roura/) │    │
│  │  - Session summaries                │    │
│  │  - User preferences                 │    │
│  │  - Project notes                    │    │
│  │  Lifetime: until deleted            │    │
│  └─────────────────────────────────────┘    │
│                                             │
└─────────────────────────────────────────────┘
```

### Session Memory Structure

```
Session:
  id: UUID
  started_at: datetime
  repo_root: Path
  messages: list[Message]
  tool_calls: list[ToolCall]
  approvals: list[Approval]
  status: running | completed | aborted | error
```

### Context Window Management

| Strategy | Description |
|----------|-------------|
| **Truncation** | Drop oldest messages when exceeding limit |
| **Summarization** | LLM summarizes older context (future) |
| **Selective injection** | Only inject relevant file contents |

---

## 7. Error Handling Model

Errors are first-class citizens. Every failure is captured, reported, and recoverable.

### Error Categories

| Category | Examples | Handling |
|----------|----------|----------|
| **LLM Error** | Timeout, malformed response, refused | Retry with backoff, then abort |
| **Tool Error** | File not found, permission denied, command failed | Report to LLM, let it adapt |
| **Validation Error** | Invalid params, schema mismatch | Report to LLM, request correction |
| **User Abort** | User says "abort" | Clean exit, preserve state |
| **System Error** | Network down, disk full | Log, notify user, exit |

### Error Response Protocol

```
1. Catch exception
2. Classify error category
3. Log full context (error, state, stack trace)
4. If recoverable: return error to LLM as tool result
5. If fatal: notify user, save session state, exit gracefully
```

### Retry Policy

| Error Type | Max Retries | Backoff |
|------------|-------------|---------|
| LLM timeout | 3 | Exponential (1s, 2s, 4s) |
| LLM rate limit | 5 | Exponential (5s, 10s, 20s, 40s, 80s) |
| Tool transient | 2 | Linear (1s, 2s) |
| Tool permanent | 0 | Immediate failure |

---

## 8. Logging Model

Every action is logged for auditability and debugging.

### Log Levels

| Level | Usage |
|-------|-------|
| **DEBUG** | Internal state, LLM prompts/responses |
| **INFO** | User-visible actions, tool calls |
| **WARN** | Recoverable issues, retries |
| **ERROR** | Failures, aborts |

### Log Destinations

```
┌─────────────────────────────────────────┐
│              LOG ROUTING                │
├─────────────────────────────────────────┤
│                                         │
│   Console (stderr)                      │
│   └── INFO and above (user-facing)      │
│                                         │
│   File (.roura/logs/YYYY-MM-DD.log)     │
│   └── DEBUG and above (full audit)      │
│                                         │
│   Session file (.roura/sessions/{id})   │
│   └── Structured JSON (replay/debug)    │
│                                         │
└─────────────────────────────────────────┘
```

### Log Entry Structure

```
LogEntry:
  timestamp: datetime (ISO 8601)
  level: DEBUG | INFO | WARN | ERROR
  session_id: UUID
  component: str (e.g., "agent", "tool.fs.write", "llm")
  event: str (e.g., "tool_executed", "approval_requested")
  data: dict (structured payload)
  duration_ms: int (optional)
```

---

## 9. Config Model

Configuration is hierarchical and repo-local.

### Config Hierarchy (Precedence: High → Low)

```
1. CLI flags          (--model qwen2.5-coder:32b)
2. Environment vars   (OLLAMA_MODEL=...)
3. Repo config        (.roura/config.toml)
4. User config        (~/.config/roura/config.toml)
5. Defaults           (hardcoded)
```

### Config Schema

```toml
# .roura/config.toml

[llm]
backend = "ollama"              # ollama | anthropic | openai (future)
base_url = "http://localhost:11434"
model = "qwen2.5-coder:32b"
temperature = 0.0               # Deterministic
timeout_seconds = 120

[agent]
max_iterations = 50             # Prevent infinite loops
auto_approve = []               # Tools to auto-approve (empty = none)

[logging]
level = "INFO"                  # DEBUG | INFO | WARN | ERROR
file_enabled = true

[git]
auto_stage = false              # Never auto-stage
require_clean = false           # Allow dirty worktree
```

### Config Commands

```bash
roura-agent config list                     # Show all config
roura-agent config get llm.model            # Get specific key
roura-agent config set llm.model "x"        # Set specific key
```

---

## 10. Git Workflow Model

The agent is deeply integrated with git.

### Repo Detection

```
On startup:
1. Find git root (walk up from cwd)
2. If no git root: warn, operate in "detached" mode
3. If git root found: load repo context
```

### Repo Context (Injected Each Turn)

```
RepoContext:
  root: Path
  branch: str
  status: GitStatus (clean | dirty | untracked | conflicts)
  recent_commits: list[Commit] (last 5)
  staged_files: list[Path]
  modified_files: list[Path]
  untracked_files: list[Path]
```

### Git Safety Rules

| Rule | Enforcement |
|------|-------------|
| Never auto-commit | Always require APPROVE_COMMIT |
| Never force-push | Tool does not support --force |
| Never rewrite history | No rebase, no amend (unless explicit) |
| Always show diff before commit | Mandatory in REPORT phase |
| Never commit secrets | Warn if .env, credentials, keys detected |

### Commit Flow

```
1. Agent proposes changes (fs.write, fs.edit)
2. User approves writes
3. Agent proposes: git.add <files>
4. User approves staging
5. Agent proposes: git.commit -m "message"
6. Agent shows: git diff --staged
7. User approves commit
8. Commit executed
9. Agent shows: git log -1, git status
```

---

## 11. Directory Structure

```
roura-agent/                    # Repository root
├── .roura/                     # Agent config (gitignored selectively)
│   ├── config.toml             # Repo-local config
│   ├── logs/                   # Session logs
│   │   └── 2026-01-23.log
│   └── sessions/               # Session snapshots
│       └── {uuid}.json
├── roura_agent/                # Python package
│   ├── __init__.py
│   ├── cli.py                  # Typer CLI entrypoint
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── loop.py             # Agent state machine
│   │   ├── state.py            # State definitions
│   │   └── planner.py          # Plan generation
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── base.py             # Abstract LLM interface
│   │   └── ollama.py           # Ollama implementation
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── base.py             # Tool base class + registry
│   │   ├── fs.py               # Filesystem tools
│   │   ├── git.py              # Git tools
│   │   └── shell.py            # Shell tools
│   ├── memory/
│   │   ├── __init__.py
│   │   ├── session.py          # Session memory
│   │   └── context.py          # Repo context
│   ├── approval/
│   │   ├── __init__.py
│   │   └── gate.py             # Approval logic
│   ├── config/
│   │   ├── __init__.py
│   │   └── loader.py           # Config hierarchy
│   └── logging/
│       ├── __init__.py
│       └── logger.py           # Structured logging
├── tests/
│   └── ...
├── pyproject.toml
└── README.md
```

---

## 12. Open Questions

| Question | Options | Recommendation |
|----------|---------|----------------|
| Should we support streaming responses? | Yes / No | **No** (simplicity first) |
| Should sessions persist across runs? | Yes / No | **Yes** (via .roura/sessions/) |
| Should we support multiple LLM backends? | Yes / No | **Later** (Ollama only for v0.2) |
| Should auto-approve be configurable per-tool? | Yes / No | **Yes** (power users) |

---

## 13. Implementation Phases

| Phase | Scope | Deliverable |
|-------|-------|-------------|
| **Phase 3** | Tool system foundation | Base tool class, fs.read, fs.list, git.status |
| **Phase 4** | Agent loop | State machine, single iteration working |
| **Phase 5** | Approval gates | All mutations gated |
| **Phase 6** | Full tool set | fs.write, fs.edit, git.add, git.commit, shell.exec |
| **Phase 7** | Memory + persistence | Session storage, context injection |
| **Phase 8** | Config system | Hierarchy, .roura/config.toml |
| **Phase 9** | Logging + audit | Structured logs, session replay |
| **Phase 10** | Polish | Error handling, UX, edge cases |

---

## 14. Non-Goals (Explicitly Out of Scope)

- Multi-file atomic transactions
- Undo/rollback system (use git)
- GUI or web interface
- Cloud sync
- Team collaboration features
- Plugin system (for now)
