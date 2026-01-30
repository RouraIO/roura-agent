"""
Roura Agent Base Agent - Foundation for specialized agents.

© Roura.io
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Any, Callable, TYPE_CHECKING

from rich.console import Console

if TYPE_CHECKING:
    from ..llm import LLMProvider
    from .executor import ExecutionContext
    from .agent_loop import AgentLoop, AgentLoopConfig


class AgentCapability(Enum):
    """Capabilities that agents can have."""
    CODE_WRITE = "code_write"           # Can write/edit code
    CODE_READ = "code_read"             # Can read and analyze code
    CODE_REVIEW = "code_review"         # Can review code quality
    TEST_WRITE = "test_write"           # Can write tests
    TEST_RUN = "test_run"               # Can run tests
    DEBUG = "debug"                     # Can debug issues
    RESEARCH = "research"               # Can search and read docs
    GIT = "git"                         # Can perform git operations
    GITHUB = "github"                   # Can interact with GitHub
    JIRA = "jira"                       # Can interact with Jira
    SHELL = "shell"                     # Can run shell commands
    FILE_SYSTEM = "file_system"         # Can read/write files
    PLAN = "plan"                       # Can create execution plans
    DELEGATE = "delegate"               # Can delegate to other agents


@dataclass
class AgentResult:
    """Result from an agent execution."""
    success: bool
    output: Any = None
    error: Optional[str] = None
    artifacts: dict = field(default_factory=dict)  # Files created, etc.
    delegated_to: Optional[str] = None  # If task was delegated
    needs_followup: bool = False
    followup_prompt: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "artifacts": self.artifacts,
            "delegated_to": self.delegated_to,
            "needs_followup": self.needs_followup,
            "followup_prompt": self.followup_prompt,
        }


@dataclass
class AgentContext:
    """Context passed to agents during execution."""
    task: str
    project_root: Optional[str] = None
    files_in_context: list[str] = field(default_factory=list)
    previous_results: list[AgentResult] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


class BaseAgent(ABC):
    """
    Base class for all specialized agents.

    Each agent has:
    - A unique name
    - A description of what it does
    - A list of capabilities
    - A system prompt tailored to its role
    - Access to specific tools (based on permissions)
    - Its own agentic loop for tool execution

    Subclasses must implement:
    - system_prompt: The system prompt for the agent
    - can_handle(): Whether agent can handle a given task

    Subclasses may override:
    - execute(): Main execution logic (default uses agentic loop)
    - allowed_tools: Set of tools this agent can use
    """

    # Override in subclasses
    name: str = "base"
    description: str = "Base agent"
    capabilities: list[AgentCapability] = []

    # Tool permissions - override in subclasses for custom permissions
    # If None, uses default permissions based on agent name
    allowed_tools: Optional[set[str]] = None

    def __init__(
        self,
        console: Optional[Console] = None,
        llm: Optional["LLMProvider"] = None,
    ):
        self.console = console or Console()
        self._llm = llm
        self._tools: list[str] = []  # Deprecated: use allowed_tools instead
        self._execution_context: Optional["ExecutionContext"] = None
        self._approval_callback: Optional[Callable[[str, dict], bool]] = None

    @property
    def llm(self) -> "LLMProvider":
        """Get LLM provider, creating default if needed."""
        if self._llm is None:
            from ..llm import get_provider
            self._llm = get_provider()
        return self._llm

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """System prompt for this agent."""
        pass

    @abstractmethod
    def can_handle(self, task: str, context: Optional[AgentContext] = None) -> tuple[bool, float]:
        """
        Check if this agent can handle the given task.

        Returns:
            (can_handle, confidence) where confidence is 0.0-1.0
        """
        pass

    def execute(self, context: AgentContext) -> AgentResult:
        """
        Execute the task using the agentic loop.

        This default implementation uses the AgentLoop to run an iterative
        tool-using loop. Subclasses can override for custom behavior.

        Args:
            context: The task context including the task description

        Returns:
            AgentResult with success/failure and any outputs
        """
        from .agent_loop import AgentLoop, AgentLoopConfig
        from .executor import ExecutionContext, ToolPermissions

        # Get allowed tools
        if self.allowed_tools:
            tools = self.allowed_tools
        else:
            tools = ToolPermissions.get_for_agent(self.name)

        # Create or use existing execution context
        exec_context = self._execution_context or ExecutionContext()
        if context.project_root:
            exec_context.project_root = context.project_root

        # Create loop configuration
        loop_config = AgentLoopConfig(
            max_iterations=self._get_max_iterations(),
            max_tool_calls_per_turn=5,
            stream_responses=True,
            show_tool_calls=True,
            show_tool_results=True,
        )

        # Create and run the agent loop
        loop = AgentLoop(
            agent_name=self.name,
            system_prompt=self.system_prompt,
            llm=self.llm,
            console=self.console,
            config=loop_config,
            allowed_tools=tools,
            execution_context=exec_context,
            approval_callback=self._approval_callback,
        )

        self.log(f"Starting task: {context.task[:50]}...")

        try:
            result = loop.run(context.task, context)
            return result
        except Exception as e:
            return AgentResult(
                success=False,
                error=f"Agent execution error: {e}",
            )

    def _get_max_iterations(self) -> int:
        """Get max iterations for this agent type."""
        # Different agents may need more/fewer iterations
        iterations = {
            'code': 10,
            'test': 8,
            'debug': 15,  # Debugging is iterative
            'research': 5,
            'git': 5,
            'review': 5,
        }
        return iterations.get(self.name, 10)

    def set_execution_context(self, context: "ExecutionContext") -> None:
        """Set shared execution context (for multi-agent scenarios)."""
        self._execution_context = context

    def set_approval_callback(self, callback: Callable[[str, dict], bool]) -> None:
        """Set callback for tool approval."""
        self._approval_callback = callback

    def get_tools(self) -> list[str]:
        """Get the list of tools this agent can use."""
        if self.allowed_tools:
            return list(self.allowed_tools)
        from .executor import ToolPermissions
        return list(ToolPermissions.get_for_agent(self.name))

    def set_tools(self, tools: list[str]) -> None:
        """Set the list of tools this agent can use."""
        self.allowed_tools = set(tools)

    def log(self, message: str, style: str = "dim") -> None:
        """Log a message to console."""
        self.console.print(f"[{style}][{self.name}] {message}[/{style}]")

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name='{self.name}'>"
