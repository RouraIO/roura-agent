"""
Roura Agent Orchestrator - Main agent that delegates to specialized agents.

© Roura.io
"""
from __future__ import annotations

import re
from typing import Optional, Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .base import (
    BaseAgent,
    AgentCapability,
    AgentContext,
    AgentResult,
)
from .registry import get_registry


class Orchestrator(BaseAgent):
    """
    Master orchestrator that analyzes tasks and delegates to specialized agents.

    The orchestrator:
    1. Analyzes incoming tasks to understand requirements
    2. Finds or creates appropriate specialized agents
    3. Delegates work and coordinates results
    4. Handles multi-step workflows across agents
    """

    name = "orchestrator"
    description = "Analyzes tasks and delegates to specialized agents"
    capabilities = [AgentCapability.PLAN, AgentCapability.DELEGATE]

    # Task patterns for routing
    TASK_PATTERNS = {
        "code": [
            r"write\s+(code|function|class|method)",
            r"implement\b",
            r"create\s+(a\s+)?(function|class|module)",
            r"add\s+(a\s+)?(feature|functionality)",
            r"refactor\b",
            r"modify\s+(the\s+)?code",
        ],
        "test": [
            r"write\s+(a\s+)?test",
            r"add\s+(a\s+)?test",
            r"test\s+(the\s+|this\s+)?",
            r"unit\s+test",
            r"integration\s+test",
            r"coverage\b",
        ],
        "debug": [
            r"debug\b",
            r"fix\s+(the\s+|this\s+)?(bug|error|issue)",
            r"troubleshoot\b",
            r"why\s+(is|does|isn't|doesn't)",
            r"not\s+working",
            r"broken\b",
        ],
        "research": [
            r"search\s+(for|the)",
            r"find\s+(information|docs|documentation)",
            r"look\s+up\b",
            r"what\s+is\b",
            r"how\s+(do|does|to)\b",
            r"explain\b",
        ],
        "git": [
            r"commit\b",
            r"push\b",
            r"pull\b",
            r"merge\b",
            r"branch\b",
            r"git\s+",
            r"version\s+control",
        ],
        "review": [
            r"review\s+(the\s+|this\s+)?code",
            r"code\s+review",
            r"check\s+(the\s+)?quality",
            r"pr\s+review",
            r"pull\s+request\s+review",
        ],
        "cursor": [
            r"cursor\b",
            r"open\s+in\s+cursor",
            r"use\s+cursor",
            r"send\s+to\s+cursor",
            r"cursor\s+composer",
        ],
        "xcode": [
            r"xcode\b",
            r"ios\b",
            r"macos\b",
            r"swift\b",
            r"xcworkspace\b",
            r"xcodeproj\b",
            r"simulator\b",
            r"build\s+(for\s+)?(ios|iphone|ipad)",
        ],
    }

    def __init__(
        self,
        console: Optional[Console] = None,
        llm: Optional[Any] = None,
        auto_create_agents: bool = True,
    ):
        super().__init__(console, llm)
        self._auto_create_agents = auto_create_agents
        self._execution_history: list[dict] = []

    @property
    def system_prompt(self) -> str:
        """System prompt for orchestrator analysis."""
        return """You are the Roura Agent Orchestrator, responsible for analyzing tasks
and delegating them to specialized agents.

Your responsibilities:
1. Analyze the user's task to understand what type of work is needed
2. Break complex tasks into smaller subtasks if necessary
3. Identify which specialized agent(s) should handle each part
4. Coordinate the execution and combine results

Available agent types:
- code: Writing and modifying code
- test: Writing and running tests
- debug: Debugging and fixing issues
- research: Searching documentation and gathering information
- git: Version control operations
- review: Code review and quality checks

When analyzing a task, respond with:
- task_type: The primary type of work needed
- subtasks: List of smaller tasks if the work should be broken down
- agents_needed: Which specialized agents should be involved
- execution_order: The order agents should execute (parallel or sequential)
"""

    def can_handle(
        self,
        task: str,
        context: Optional[AgentContext] = None,
    ) -> tuple[bool, float]:
        """Orchestrator can handle any task by delegating."""
        # Orchestrator always returns true with moderate confidence
        # Specialized agents should return higher confidence for their domains
        return True, 0.5

    def execute(self, context: AgentContext) -> AgentResult:
        """
        Analyze and delegate the task.

        Steps:
        1. Analyze task to determine type and complexity
        2. Find or create appropriate agent(s)
        3. Delegate and collect results
        4. Return combined result
        """
        task = context.task
        self.log(f"Analyzing task: {task[:50]}...")

        # Step 1: Analyze task type
        task_analysis = self._analyze_task(task)
        self.log(f"Task type: {task_analysis['primary_type']}")

        # Step 2: Find capable agent
        registry = get_registry()
        agent = registry.best_agent(task, context)

        if agent is None and self._auto_create_agents:
            # Create a dynamic agent for this task type
            agent = self._create_agent_for_type(task_analysis["primary_type"])
            if agent:
                registry.register(agent)
                self.log(f"Created new agent: {agent.name}")

        if agent is None:
            return AgentResult(
                success=False,
                error=f"No agent available for task type: {task_analysis['primary_type']}",
            )

        # Step 3: Delegate to agent
        self.log(f"Delegating to: {agent.name}")
        self._show_delegation(agent, task_analysis)

        result = agent.execute(context)

        # Track execution
        self._execution_history.append({
            "task": task,
            "analysis": task_analysis,
            "agent": agent.name,
            "success": result.success,
        })

        # Step 4: Handle follow-ups if needed
        if result.needs_followup and result.followup_prompt:
            followup_context = AgentContext(
                task=result.followup_prompt,
                project_root=context.project_root,
                files_in_context=context.files_in_context,
                previous_results=[result],
                metadata=context.metadata,
            )
            return self.execute(followup_context)

        return result

    def _analyze_task(self, task: str) -> dict:
        """
        Analyze task to determine type and requirements.

        Uses pattern matching for fast local analysis.
        Can be enhanced with LLM for complex cases.
        """
        task_lower = task.lower()
        scores: dict[str, int] = {}

        # Score each task type based on pattern matches
        for task_type, patterns in self.TASK_PATTERNS.items():
            score = 0
            for pattern in patterns:
                if re.search(pattern, task_lower):
                    score += 1
            if score > 0:
                scores[task_type] = score

        # Determine primary type
        if scores:
            primary_type = max(scores, key=scores.get)
        else:
            # Default to code for unclassified tasks
            primary_type = "code"

        return {
            "primary_type": primary_type,
            "scores": scores,
            "is_complex": len(scores) > 1,
            "all_types": list(scores.keys()),
        }

    def _create_agent_for_type(self, task_type: str) -> Optional[BaseAgent]:
        """
        Dynamically create an agent for a task type.

        Returns a specialized agent instance.
        """
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
        )

        agent_classes = {
            "code": CodeAgent,
            "test": TestAgent,
            "debug": DebugAgent,
            "research": ResearchAgent,
            "git": GitAgent,
            "review": ReviewAgent,
            "cursor": CursorAgent,
            "xcode": XcodeAgent,
        }

        agent_class = agent_classes.get(task_type)
        if agent_class:
            return agent_class(console=self.console, llm=self._llm)
        return None

    def _show_delegation(self, agent: BaseAgent, analysis: dict) -> None:
        """Display delegation information."""
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column(style="dim")
        table.add_column()

        table.add_row("Agent", f"[cyan]{agent.name}[/cyan]")
        table.add_row("Task Type", analysis["primary_type"])
        if analysis["is_complex"]:
            table.add_row("Related", ", ".join(analysis["all_types"]))

        self.console.print(Panel(
            table,
            title="[bold]Delegating Task[/bold]",
            border_style="blue",
        ))

    def get_execution_history(self) -> list[dict]:
        """Get the history of delegated executions."""
        return self._execution_history.copy()

    def clear_history(self) -> None:
        """Clear execution history."""
        self._execution_history.clear()
