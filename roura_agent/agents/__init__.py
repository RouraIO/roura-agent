"""
Roura Agent Multi-Agent System - Orchestrated specialized agents.

This module provides:
- Base agent class for specialized agents
- Agent registry for dynamic agent management
- Orchestrator for task delegation
- Pre-built specialized agents (Code, Test, Debug, Research, etc.)
- Tool execution framework for agents
- Agent-level agentic loops
- IDE integrations (Cursor, Xcode)
- Inter-agent messaging system

© Roura.io
"""
from .base import BaseAgent, AgentCapability, AgentContext, AgentResult
from .registry import AgentRegistry, get_registry
from .orchestrator import Orchestrator
from .executor import (
    ToolExecutorMixin,
    ExecutionContext,
    FileContext,
    ToolPermissions,
)
from .agent_loop import (
    AgentLoop,
    AgentLoopConfig,
)
from .context import (
    SharedExecutionContext,
    FileSnapshot,
    ModificationRecord,
    get_shared_context,
)
from .approval import (
    ApprovalManager,
    ApprovalMode,
    ApprovalRequest,
    ApprovalDecision,
    get_approval_manager,
    create_console_approval_callback,
)
from .constraints import (
    ConstraintChecker,
    ConstraintViolation,
    ConstraintResult,
    ViolationResult,
    AgentConstraints,
    get_constraint_checker,
)
from .specialized import (
    CodeAgent,
    TestAgent,
    DebugAgent,
    ResearchAgent,
    GitAgent,
    ReviewAgent,
)
from .integrations import (
    CursorAgent,
    XcodeAgent,
    IDEBridgeAgent,
)
from .cursor_bridge import (
    CursorBridge,
    CursorTask,
    CursorTaskStatus,
    create_cursor_bridge,
)
from .messaging import (
    MessageBus,
    AgentMessage,
    MessagePriority,
    MessageStatus,
    get_message_bus,
    send_to_agent,
)
from .parallel import (
    ParallelExecutor,
    ParallelTask,
    TaskStatus,
    ExecutionPlan,
    DependencyGraph,
    ResourceManager,
    ParallelAgentRunner,
    run_agents_parallel,
)


def initialize_agents(console=None, llm=None) -> Orchestrator:
    """
    Initialize the agent system with all specialized agents.

    Returns the orchestrator ready for task delegation.
    """
    registry = get_registry()

    # Get shared execution context (singleton) for all agents
    shared_context = get_shared_context()

    # Set up approval manager with console callback if available
    approval_manager = get_approval_manager()
    if console:
        approval_manager.set_callback(create_console_approval_callback(console))

    # Set up constraint checker with shared context
    constraint_checker = get_constraint_checker()
    constraint_checker.set_context(shared_context)

    # Create and register all specialized agents
    agents = [
        CodeAgent(console=console, llm=llm),
        TestAgent(console=console, llm=llm),
        DebugAgent(console=console, llm=llm),
        ResearchAgent(console=console, llm=llm),
        GitAgent(console=console, llm=llm),
        ReviewAgent(console=console, llm=llm),
        CursorAgent(console=console, llm=llm),
        XcodeAgent(console=console, llm=llm),
        IDEBridgeAgent(console=console, llm=llm),
    ]

    # Set shared execution context for all agents
    for agent in agents:
        agent.set_execution_context(shared_context)
        registry.register(agent)

    # Initialize message bus
    bus = get_message_bus(console)

    # Register agent handlers with message bus
    for agent in agents:
        bus.register_handler(
            agent.name,
            lambda msg, a=agent: a.execute(
                AgentContext(
                    task=msg.task,
                    metadata=msg.context or {},
                )
            ),
        )

    # Create and return orchestrator
    orchestrator = Orchestrator(console=console, llm=llm)

    # Register orchestrator with message bus
    bus.register_handler(
        "orchestrator",
        lambda msg: orchestrator.execute(
            AgentContext(task=msg.task, metadata=msg.context or {})
        ),
    )

    return orchestrator


__all__ = [
    # Base
    "BaseAgent",
    "AgentCapability",
    "AgentContext",
    "AgentResult",
    # Registry
    "AgentRegistry",
    "get_registry",
    # Orchestrator
    "Orchestrator",
    # Tool Execution
    "ToolExecutorMixin",
    "ExecutionContext",
    "FileContext",
    "ToolPermissions",
    # Agent Loop
    "AgentLoop",
    "AgentLoopConfig",
    # Shared Context (Phase 3)
    "SharedExecutionContext",
    "FileSnapshot",
    "ModificationRecord",
    "get_shared_context",
    # Approval Manager (Phase 3)
    "ApprovalManager",
    "ApprovalMode",
    "ApprovalRequest",
    "ApprovalDecision",
    "get_approval_manager",
    "create_console_approval_callback",
    # Constraint Checker (Phase 3)
    "ConstraintChecker",
    "ConstraintViolation",
    "ConstraintResult",
    "ViolationResult",
    "AgentConstraints",
    "get_constraint_checker",
    # Specialized agents
    "CodeAgent",
    "TestAgent",
    "DebugAgent",
    "ResearchAgent",
    "GitAgent",
    "ReviewAgent",
    # IDE Integrations
    "CursorAgent",
    "XcodeAgent",
    "IDEBridgeAgent",
    # Cursor Bridge (Phase 5)
    "CursorBridge",
    "CursorTask",
    "CursorTaskStatus",
    "create_cursor_bridge",
    # Messaging
    "MessageBus",
    "AgentMessage",
    "MessagePriority",
    "MessageStatus",
    "get_message_bus",
    "send_to_agent",
    # Parallel Execution (Phase 4)
    "ParallelExecutor",
    "ParallelTask",
    "TaskStatus",
    "ExecutionPlan",
    "DependencyGraph",
    "ResourceManager",
    "ParallelAgentRunner",
    "run_agents_parallel",
    # Initialization
    "initialize_agents",
]
