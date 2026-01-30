# Roura Agent v2.0 Roadmap

## Mission: Achieve Feature Parity with Claude Code

This document outlines the implementation plan to make Roura Agent a world-class agentic coding assistant.

---

## Phase 1: Agentic Tool Execution for Specialized Agents
**Priority: CRITICAL | Effort: Large**

### Problem
Specialized agents (CodeAgent, TestAgent, etc.) just call the LLM once and return text. They can't actually read files, write code, or run commands.

### Solution
Create a `ToolExecutor` mixin/base that gives every agent the ability to:
1. Access the tool registry
2. Execute tools with proper approval flows
3. Track file reads/writes
4. Support undo operations

### Implementation Steps

```
1. Create `roura_agent/agents/executor.py`
   - ToolExecutorMixin class
   - Methods: execute_tool(), get_tools_schema(), track_file_read()
   - Integrates with existing tools.base.registry

2. Update BaseAgent to inherit ToolExecutorMixin
   - Add _tool_registry reference
   - Add _file_context tracking
   - Add approval callback support

3. Update each specialized agent
   - CodeAgent: Can use fs.read, fs.write, fs.edit
   - TestAgent: Can use fs.read, fs.write, shell.exec (pytest)
   - DebugAgent: Can use fs.read, shell.exec, fs.edit
   - GitAgent: Can use git.* tools
   - etc.

4. Tool permission model
   - Each agent declares which tools it can use
   - Orchestrator enforces permissions
   - Prevents test agent from committing, etc.
```

### Files to Create/Modify
- `roura_agent/agents/executor.py` (NEW)
- `roura_agent/agents/base.py` (MODIFY)
- `roura_agent/agents/specialized.py` (MODIFY)

---

## Phase 2: Agentic Loop for Each Agent
**Priority: CRITICAL | Effort: Large**

### Problem
Agents do one LLM call and return. They can't iterate: call tool → see result → decide next step → repeat.

### Solution
Each agent gets its own mini agentic loop, similar to `AgentLoop._process_turn()`.

### Implementation Steps

```
1. Create `roura_agent/agents/loop.py`
   - AgentExecutionLoop class
   - Handles: LLM call → tool execution → result processing → iteration
   - Configurable max_iterations per agent
   - Shares streaming/display logic with main loop

2. Add loop to BaseAgent
   - BaseAgent.run_loop(context) -> AgentResult
   - Replaces simple execute() for complex tasks
   - Simple tasks can still use single-shot execute()

3. Loop features
   - Tool call accumulation (multiple tools per turn)
   - Result feeding back to LLM
   - Interruption support (ESC)
   - Progress callbacks for UI updates

4. Agent-specific loop configs
   - CodeAgent: max 10 iterations, can use fs.*, shell.exec
   - TestAgent: max 5 iterations, focused on test execution
   - DebugAgent: max 15 iterations (debugging is iterative)
```

### Architecture
```
User Input
    ↓
Orchestrator (analyzes, routes)
    ↓
Specialized Agent
    ↓
Agent's Own Loop:
    ├── LLM Call (with tools schema)
    ├── Tool Execution (fs.read, fs.write, etc.)
    ├── Result Processing
    └── Iterate until done or max_iterations
    ↓
AgentResult
    ↓
Back to Orchestrator (for follow-ups or completion)
```

### Files to Create/Modify
- `roura_agent/agents/loop.py` (NEW)
- `roura_agent/agents/base.py` (MODIFY)
- `roura_agent/agents/specialized.py` (MODIFY)

---

## Phase 3: Shared Tool Infrastructure
**Priority: HIGH | Effort: Medium**

### Problem
Main AgentLoop has approval flows, undo tracking, file read requirements - agents bypass all of this.

### Solution
Extract shared infrastructure into reusable components that both the main loop and agents use.

### Implementation Steps

```
1. Create `roura_agent/agents/context.py`
   - SharedExecutionContext class
   - Tracks: files_read, files_modified, undo_stack
   - Shared across all agents in a session
   - Persists between agent handoffs

2. Create `roura_agent/agents/approval.py`
   - ApprovalManager class
   - Handles: risk assessment, user prompts, "approve all" mode
   - Configurable per-agent approval requirements
   - Callback-based for UI flexibility

3. Create `roura_agent/agents/constraints.py`
   - ConstraintChecker class
   - Enforces: "must read before write", file permissions
   - Agent-specific constraints (TestAgent can't modify src/)

4. Wire everything together
   - Orchestrator creates SharedExecutionContext
   - Passes to each agent
   - Agents use shared approval/constraint systems
```

### Files to Create/Modify
- `roura_agent/agents/context.py` (NEW)
- `roura_agent/agents/approval.py` (NEW)
- `roura_agent/agents/constraints.py` (NEW)
- `roura_agent/agents/orchestrator.py` (MODIFY)

---

## Phase 4: Parallel Agent Execution
**Priority: HIGH | Effort: Medium**

### Problem
Agents run sequentially. Can't have CodeAgent writing while TestAgent validates.

### Solution
Async execution with proper coordination.

### Implementation Steps

```
1. Update MessageBus for async
   - Use asyncio or threading with proper locks
   - Message queue with worker pool
   - Results aggregation

2. Create `roura_agent/agents/parallel.py`
   - ParallelExecutor class
   - Methods: run_parallel([agents], [tasks])
   - Handles: task dependencies, result merging, error handling

3. Dependency graph support
   - Some tasks depend on others
   - Example: TestAgent waits for CodeAgent to finish
   - DAG-based execution order

4. UI updates for parallel work
   - Show multiple agents working simultaneously
   - Progress for each agent
   - Merged results display

5. Resource management
   - Limit concurrent LLM calls (API rate limits)
   - File locking (prevent concurrent writes to same file)
   - Memory management for large contexts
```

### Example Flow
```
User: "Add a login feature with tests"
    ↓
Orchestrator spawns:
  ├── CodeAgent (write login code) ──────┐
  │                                       ├── Wait for code
  └── [blocked] TestAgent (write tests) ──┘
                    ↓
              TestAgent runs after CodeAgent completes
                    ↓
              Merged result to user
```

### Files to Create/Modify
- `roura_agent/agents/parallel.py` (NEW)
- `roura_agent/agents/messaging.py` (MODIFY)
- `roura_agent/agents/orchestrator.py` (MODIFY)

---

## Phase 5: Deep Cursor Integration
**Priority: MEDIUM | Effort: Large**

### Problem
Current Cursor integration just opens files. Can't send prompts or get responses.

### Challenge
Cursor doesn't have a public API for Composer. We need creative solutions.

### Solution Options

```
Option A: File-Based Protocol
1. Create a .roura/ directory in project
2. Write task files: .roura/tasks/001-implement-auth.md
3. Cursor user opens file, uses Composer
4. Watch for changes to detect completion
5. Parse Cursor's output from git diff

Option B: Clipboard Bridge
1. Copy prompt to clipboard
2. Open Cursor with applescript/osascript
3. Paste and trigger Composer (Cmd+K)
4. Monitor file changes for completion

Option C: Extension Bridge (Best but complex)
1. Create VS Code/Cursor extension
2. Extension exposes local HTTP API
3. Roura Agent calls extension API
4. Extension triggers Composer, returns results

Option D: MCP Server for Cursor (Future)
1. Wait for Cursor to support MCP
2. Create MCP server that Cursor connects to
3. Bidirectional communication
```

### Implementation (Option A - Pragmatic)

```
1. CursorBridge class
   - create_task_file(task, context) -> path
   - watch_for_completion(task_id) -> result
   - parse_changes() -> diff

2. Workflow
   - Roura: "Send this to Cursor for implementation"
   - Creates .roura/tasks/implement-feature.md with:
     - Task description
     - Relevant file contents
     - Expected output format
   - Opens file in Cursor
   - Watches for file changes
   - Parses result when user marks complete

3. Status tracking
   - .roura/status.json tracks pending tasks
   - Cursor tasks show in /tasks command
   - Completion detection via file watchers
```

### Files to Create/Modify
- `roura_agent/agents/cursor_bridge.py` (NEW)
- `roura_agent/agents/integrations.py` (MODIFY)

---

## Phase 6: Claude Code Feature Parity
**Priority: MEDIUM | Effort: Large**

### Missing Features

#### 6.1 MCP Server Support
```
1. Create `roura_agent/mcp/` module
   - client.py: Connect to MCP servers
   - protocol.py: MCP message handling
   - tools.py: Convert MCP tools to Roura tools

2. Configuration
   - ~/.roura/mcp.json for server configs
   - Auto-discovery of local MCP servers

3. Integration
   - MCP tools appear in tool registry
   - Agents can use MCP tools like native tools
```

#### 6.2 Web Search & Fetch
```
1. Create web tools
   - tools/web.py: web_search, web_fetch
   - Use DuckDuckGo or similar for search
   - HTML to markdown conversion

2. Research agent enhancement
   - ResearchAgent gets web tools
   - Can search docs, Stack Overflow, etc.
```

#### 6.3 Image Understanding
```
1. Multimodal support
   - Update LLM providers to support images
   - Image tools: analyze_image, screenshot

2. Use cases
   - "What's in this screenshot?"
   - "Fix the UI bug shown in this image"
   - Design review from mockups
```

#### 6.4 Jupyter Notebook Support
```
1. Notebook tools
   - tools/notebook.py: read_notebook, edit_cell, run_cell
   - Parse .ipynb JSON format

2. Data science agent
   - New DataAgent for notebooks
   - Can execute cells, analyze output
```

### Files to Create
- `roura_agent/mcp/` (NEW directory)
- `roura_agent/tools/web.py` (NEW)
- `roura_agent/tools/notebook.py` (NEW)
- `roura_agent/agents/data_agent.py` (NEW)

---

## Implementation Order

### Sprint 1: Foundation (Phases 1-2)
**Goal: Agents can actually DO things**

1. ToolExecutorMixin
2. Agent-level agentic loops
3. CodeAgent fully functional with tools
4. TestAgent can run pytest

### Sprint 2: Infrastructure (Phase 3)
**Goal: Shared systems, proper constraints**

1. SharedExecutionContext
2. ApprovalManager
3. ConstraintChecker
4. Wire into all agents

### Sprint 3: Parallelism (Phase 4)
**Goal: Concurrent agent execution**

1. Async MessageBus
2. ParallelExecutor
3. Dependency graph
4. UI for parallel progress

### Sprint 4: Integrations (Phases 5-6)
**Goal: External tool support**

1. Cursor bridge (file-based)
2. Web search/fetch
3. MCP client basics
4. Image support

### Sprint 5: Polish
**Goal: Production ready**

1. Notebook support
2. Error recovery
3. Performance optimization
4. Documentation

---

## Success Metrics

| Feature | Metric |
|---------|--------|
| Tool Execution | Agents complete 90% of tasks without falling back to main loop |
| Agentic Loop | Average 3+ tool calls per agent task |
| Parallel | 2x speedup on multi-file tasks |
| Cursor | Successful round-trip task completion |
| MCP | 3+ MCP servers working |

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         User Input                               │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                        Orchestrator                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │ Task        │  │ Agent       │  │ Parallel                │  │
│  │ Analyzer    │→ │ Router      │→ │ Executor                │  │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                                │
                ┌───────────────┼───────────────┐
                ▼               ▼               ▼
┌───────────────────┐ ┌───────────────────┐ ┌───────────────────┐
│    Code Agent     │ │    Test Agent     │ │   Cursor Agent    │
│  ┌─────────────┐  │ │  ┌─────────────┐  │ │  ┌─────────────┐  │
│  │ Agent Loop  │  │ │  │ Agent Loop  │  │ │  │ Cursor      │  │
│  │  ┌───────┐  │  │ │  │  ┌───────┐  │  │ │  │ Bridge      │  │
│  │  │ Tools │  │  │ │  │  │ Tools │  │  │ │  └─────────────┘  │
│  │  └───────┘  │  │ │  │  └───────┘  │  │ │                   │
│  └─────────────┘  │ │  └─────────────┘  │ │                   │
└───────────────────┘ └───────────────────┘ └───────────────────┘
         │                    │                      │
         └────────────────────┼──────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Shared Infrastructure                          │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────────────────┐ │
│  │ Tool         │ │ Execution    │ │ Approval                 │ │
│  │ Registry     │ │ Context      │ │ Manager                  │ │
│  └──────────────┘ └──────────────┘ └──────────────────────────┘ │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────────────────┐ │
│  │ Message      │ │ MCP          │ │ Web                      │ │
│  │ Bus          │ │ Client       │ │ Tools                    │ │
│  └──────────────┘ └──────────────┘ └──────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

---

## Next Steps

Ready to begin Sprint 1? Start with:
1. `roura_agent/agents/executor.py` - ToolExecutorMixin
2. Update `BaseAgent` to use it
3. Give `CodeAgent` real tool execution

This is the foundation everything else builds on.
